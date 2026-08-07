/**
 * AST Bridge - Node.js side
 * 
 * Persistent process that reads JSON commands from stdin (one per line),
 * parses JS/TS with @babel/parser or WXML with htmlparser2,
 * and writes JSON responses to stdout (one per line).
 * 
 * Protocol:
 *   Request:  {"id": 1, "type": "js"|"wxml", "content": "...", "filename": "..."}
 *   Response: {"id": 1, "ok": true, "data": {...}}
 *   Error:    {"id": 1, "ok": false, "error": "..."}
 * 
 * JS data structure:
 *   {
 *     functions: [{name, line, endLine, params, isAsync, isArrow, isEmpty, isMethod, parentName}],
 *     calls: [{name, line, full_name, args_count, is_member, member_obj}],
 *     imports: [{source, line, is_default, specifiers, is_require}],
 *     consoleCalls: [{method, line, col}],
 *     emptyFunctions: [{name, line, hasTodo}],
 *     setDataCalls: [{line, keys: [...]}],
 *     memberAssignments: [{obj, prop, line}],
 *   }
 * 
 * WXML data structure:
 *   {
 *     tags: [{name, line, attrs: {key: value}, selfClosing, children_count}],
 *     bindings: [{event, method, line, tag}],
 *     wxForTags: [{line, hasKey, keyName, list_expr, tag}],
 *     images: [{line, hasLazyLoad, src}],
 *     mustacheCount: {open, close},
 *   }
 */

const readline = require('readline');

let babelParser, babelTraverse, htmlparser2;

try {
  babelParser = require('@babel/parser');
  babelTraverse = require('@babel/traverse').default;
} catch (_babelErr) {
  // Babel not available, fallback to regex-based parsing
  babelParser = null;
  babelTraverse = null;
}

try {
  htmlparser2 = require('htmlparser2');
} catch (_htmlErr) {
  // htmlparser2 not available, WXML parsing disabled
  htmlparser2 = null;
}



/** Check if a function body is effectively empty */
function isEmptyBody(body) {
  if (!body || !body.body || body.body.length === 0) return true;
  if (body.body.length === 1) {
    const stmt = body.body[0];
    if (stmt.type === 'EmptyStatement') return true;
    if (stmt.type === 'ReturnStatement' && stmt.argument == null) return true;
  }
  return false;
}

/** Build dotted member chain string from a MemberExpression node */
function getMemberChain(node) {
  const parts = [];
  let current = node;
  while (current && current.type === 'MemberExpression') {
    if (current.property) {
      parts.unshift(current.property.name || current.property.value || '');
    }
    current = current.object;
  }
  if (current) {
    if (current.type === 'ThisExpression') parts.unshift('this');
    else if (current.type === 'Identifier') parts.unshift(current.name);
    else if (current.type === 'StringLiteral') parts.unshift(current.value);
  }
  return parts.join('.');
}

/** Get object name from a MemberExpression's object node */
function getMemberObjectName(objectNode) {
  if (!objectNode) return '';
  if (objectNode.type === 'ThisExpression') return 'this';
  if (objectNode.type === 'Identifier') return objectNode.name;
  return '';
}

/** Check for TODO/FIXME markers near a given line */
function hasTodoNearby(lineNum, lines, range) {
  if (range === undefined) range = 3;
  var start = Math.max(0, lineNum - 1 - range);
  var end = Math.min(lines.length, lineNum + range);
  for (var idx = start; idx < end; idx++) {
    var lower = (lines[idx] || '').toLowerCase();
    if (lower.includes('todo') || lower.includes('fixme') ||
        lower.includes('not implemented') || lower.includes('implement') ||
        lower.includes('placeholder') || lower.includes('占位') || lower.includes('未实现')) {
      return true;
    }
  }
  return false;
}

/** Extract arrow function name from its parent AST context */
function getArrowFunctionName(parent) {
  if (!parent) return 'anonymous';
  if (parent.type === 'VariableDeclarator' && parent.id) return parent.id.name || 'anonymous';
  if (parent.type === 'ObjectProperty' && parent.key) return parent.key.name || 'anonymous';
  if (parent.type === 'AssignmentExpression' && parent.left && parent.left.property) {
    return parent.left.property.name || 'anonymous';
  }
  return 'anonymous';
}

/** Analyze a CallExpression callee and return structured info */
function analyzeCallee(callee) {
  if (callee.type === 'Identifier') {
    return { name: callee.name, fullName: callee.name, isMember: false, memberObj: '' };
  }
  if (callee.type === 'MemberExpression') {
    return {
      name: callee.property ? (callee.property.name || '') : '',
      fullName: getMemberChain(callee),
      isMember: true,
      memberObj: getMemberObjectName(callee.object),
    };
  }
  return { name: '', fullName: '', isMember: false, memberObj: '' };
}

/** Extract setData keys from the first argument of a call */
function extractSetDataKeys(args) {
  if (!args || args.length === 0) return [];
  var arg = args[0];
  if (arg.type !== 'ObjectExpression') return [];
  return arg.properties.map(function(p) {
    if (!p.key) return '?';
    if (p.key.type === 'Identifier') return p.key.name;
    if (p.key.type === 'StringLiteral') return p.key.value;
    return '?';
  });
}

/** Get source line number at a character offset */
function getLineAt(content, offset) {
  var line = 1;
  for (var idx = 0; idx < offset && idx < content.length; idx++) {
    if (content[idx] === '\n') line++;
  }
  return line;
}

/** Get parent object name (e.g., Page, Component) from an ObjectMethod path */
function getParentObjectName(path) {
  var grandParent = path.parentPath && path.parentPath.parentPath;
  if (!grandParent || grandParent.node.type !== 'CallExpression') return '';
  var callee = grandParent.node.callee;
  return (callee && callee.name) ? callee.name : '';
}

/** Extract event binding info from a WXML attribute, or null if not a binding */
function extractBinding(key, value, line, tagName) {
  // Match bind/catch event pattern
  var bindMatch = key.match(/^(?:bind|catch)(\w+)$/);
  if (!bindMatch) { return null; }
  
  var rawValue = value.trim();
  // Skip dynamic bindings like {{handler}}
  var CHAR_OPEN_BRACE = 123; // '{'
  var char0 = rawValue.charCodeAt(0);
  var char1 = rawValue.charCodeAt(1);
  if (char0 === CHAR_OPEN_BRACE && char1 === CHAR_OPEN_BRACE) { return null; }
  
  // Extract and validate method name
  var nameMatch = rawValue.match(/^[a-zA-Z_$][\w$]*/);
  var methodName = nameMatch ? nameMatch[0] : '';
  var isValidName = methodName && /^[a-zA-Z_$][\w$]*$/.test(methodName);
  
  if (!isValidName) { return null; }
  
  // Build and return binding record
  var result = {
    event: bindMatch[1],
    method: methodName,
    raw: rawValue,
    line: line,
    tag: tagName
  };
  return result;
}

/** Copy attribs object to plain object */
function copyAttribs(attribs) {
  var attrs = {};
  for (var k in attribs) attrs[k] = attribs[k];
  return attrs;
}

/** Build a WXML record (tag, wx:for, or image) - unified factory to avoid code duplication */
function makeWxmlRecord(kind, line, attrsOrName, extra) {
  if (kind === 'tag') {
    return { kind: 'tag', name: attrsOrName, line: line, attrs: extra, selfClosing: false };
  }
  if (kind === 'wxFor') {
    var attrs = attrsOrName;
    return {
      kind: 'wxFor', line: line, hasKey: 'wx:key' in attrs,
      keyName: attrs['wx:key'] || '',
      list_expr: attrs['wx:for'] || '', tag: extra,
    };
  }
  if (kind === 'image') {
    return { kind: 'image', line: line, hasLazyLoad: 'lazy-load' in attrsOrName, src: attrsOrName['src'] || '' };
  }
}

/** Process a WXML open tag: record tag, bindings, wx:for, and image info */
function handleWxmlOpenTag(result, name, attribs, line) {
  var attrs = copyAttribs(attribs);
  result.tags.push(makeWxmlRecord('tag', line, name, attrs));

  // Extract event bindings
  Object.keys(attrs).forEach(function(key) {
    var binding = extractBinding(key, attrs[key], line, name);
    if (binding) result.bindings.push(binding);
  });

  // wx:for tracking
  if ('wx:for' in attrs || 'wx:for-item' in attrs) {
    result.wxForTags.push(makeWxmlRecord('wxFor', line, attrs, name));
  }

  // Image tracking
  if (name === 'image') {
    result.images.push(makeWxmlRecord('image', line, attrs));
  }
}


module.exports = {
  isEmptyBody,
  getMemberChain,
  getMemberObjectName,
  hasTodoNearby,
  getArrowFunctionName,
  analyzeCallee,
  extractSetDataKeys,
  getLineAt,
  getParentObjectName,
  extractBinding,
  copyAttribs,
  makeWxmlRecord,
  handleWxmlOpenTag
};
