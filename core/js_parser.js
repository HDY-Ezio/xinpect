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

const helpers = require("./ast_helpers");
const { isEmptyBody, getMemberChain, getMemberObjectName, hasTodoNearby, getArrowFunctionName } = helpers;


// Babel parser configuration (extracted to reduce nesting in parseJS)
var BABEL_PARSE_OPTIONS = {
  sourceType: 'unambiguous',
  plugins: [
    'jsx', 'typescript', 'objectRestSpread', 'classProperties',
    'asyncGenerators', 'dynamicImport', 'optionalChaining',
    'nullishCoalescingOperator',
  ],
  errorRecovery: true,
  tokens: false,
};

/** Create an empty JS parse result object */
function createParseResult() {
  return {
    functions: [], calls: [], imports: [],
    consoleCalls: [], emptyFunctions: [],
    setDataCalls: [], memberAssignments: [],
  };
}

/** Handle CallExpression visitor - extracted to reduce nesting depth */
function handleCallExpression(node, result) {
  var info = analyzeCallee(node.callee);
  var name = info.name;
  var fullName = info.fullName;
  var isMember = info.isMember;
  var memberObj = info.memberObj;

  // Record all named calls
  if (name) {
    result.calls.push({
      name: name,
      full_name: fullName,
      line: getNodeLoc(node, 'line'),
      col: getNodeLoc(node, 'column'),
      args_count: (node.arguments || []).length,
      is_member: isMember,
      member_obj: memberObj,
    });
  }

  // Console calls: merge conditions to reduce nesting
  if (isMember && memberObj === 'console' &&
      ['log', 'debug', 'trace', 'info', 'warn', 'error'].includes(name)) {
    result.consoleCalls.push({
      method: name,
      line: getNodeLoc(node, 'line'),
      col: getNodeLoc(node, 'column'),
    });
  }

  // setData calls (this.setData) - delegate key extraction
  if (isMember && fullName === 'this.setData') {
    result.setDataCalls.push({
      line: getNodeLoc(node, 'line'),
      keys: extractSetDataKeys(node.arguments),
    });
  }

  // require() calls (merged from separate traversal)
  if (node.callee.type === 'Identifier' && node.callee.name === 'require' &&
      node.arguments && node.arguments.length > 0 &&
      node.arguments[0].type === 'StringLiteral') {
    result.imports.push({
      source: node.arguments[0].value,
      line: getNodeLoc(node, 'line'),
      is_default: false,
      specifiers: [],
      is_require: true,
    });
  }
}

/** Handle ImportDeclaration visitor - extracted to reduce nesting depth */
function handleImportDeclaration(node, result) {
  var specifiers = (node.specifiers || []).map(function(s) {
    if (s.type === 'DefaultSpecifier') return { type: 'default', local: s.local?.name || '' };
    if (s.type === 'NamespaceSpecifier') return { type: 'namespace', local: s.local?.name || '' };
    if (s.type === 'ImportSpecifier') return { type: 'named', local: s.local?.name || '', imported: s.imported?.name || '' };
    return { type: 'unknown' };
  });
  result.imports.push({
    source: node.source ? node.source.value : '',
    line: getNodeLoc(node, 'line'),
    is_default: specifiers.some(function(s) { return s.type === 'default'; }),
    specifiers: specifiers,
    is_require: false,
  });
}

/** Get source position (line or column) from a node's loc (safe accessor) */
function getNodeLoc(node, prop) {
  return node.loc ? node.loc.start[prop] : 0;
}

function parseJS(content, filename) {
  if (filename === undefined) filename = '';
  if (!babelParser || !babelTraverse) {
    return { error: 'Babel parser not available' };
  }

  var ast;
  try {
    ast = babelParser.parse(content, BABEL_PARSE_OPTIONS);
  } catch (e) {
    return { error: e.message };
  }

  var result = createParseResult();

  var lines = content.split('\n');

  /** Record a function node and optionally check for empty+todo */
  function recordFunction(name, node, opts) {
    if (!opts) opts = {};
    var isEmpty = isEmptyBody(node.body);
    var line = getNodeLoc(node, 'line');
    result.functions.push({
      name: name,
      line: line,
      endLine: node.loc ? node.loc.end.line : 0,
      params: (node.params || []).map(function(p) { return p.name || ''; }),
      isAsync: node.async || false,
      isArrow: opts.isArrow || false,
      isEmpty: isEmpty,
      isMethod: opts.isMethod || false,
      parentName: opts.parentName || '',
    });
    if (!opts.skipEmptyCheck && isEmpty && hasTodoNearby(line, lines)) {
      result.emptyFunctions.push({ name: name, line: line, hasTodo: true });
    }
  }

  // Single traversal covering all JS visitors
  babelTraverse(ast, {
    FunctionDeclaration: function(path) {
      var name = path.node.id ? path.node.id.name : 'anonymous';
      recordFunction(name, path.node);
    },

    ArrowFunctionExpression: function(path) {
      // Skip callbacks inside call expressions
      if (path.parent && path.parent.type === 'CallExpression') return;
      var name = getArrowFunctionName(path.parent);
      recordFunction(name, path.node, { isArrow: true });
    },

    // v1.23.0 FP-02: FunctionExpression in ObjectProperty
    // Handles: { name: function(e) {}, name: function (e) {} }
    FunctionExpression: function(path) {
      // Only handle when parent is ObjectProperty (non-shorthand)
      if (!path.parent || path.parent.type !== 'ObjectProperty') return;
      var key = path.parent.key;
      var name = key ? (key.name || key.value || 'anonymous') : 'anonymous';
      recordFunction(name, path.node, { isMethod: true });
    },

    // Object methods: { name() {}, async name() {} }
    ObjectMethod: function(path) {
      var node = path.node;
      var name = node.key ? (node.key.name || node.key.value || 'anonymous') : 'anonymous';
      var parentName = getParentObjectName(path);
      recordFunction(name, node, { isMethod: true, parentName: parentName });
    },

    // Class methods
    ClassMethod: function(path) {
      var node = path.node;
      var name = node.key ? (node.key.name || 'anonymous') : 'anonymous';
      // ClassMethod does not check emptyFunctions (original behavior)
      recordFunction(name, node, { isMethod: true, skipEmptyCheck: true });
    },

    // Function calls (including require, console, setData)
    CallExpression: function(path) { handleCallExpression(path.node, result); },

    // Import declarations
    ImportDeclaration: function(path) { handleImportDeclaration(path.node, result); },

    // Member assignments (this.data.xxx = ...) - merged from separate traversal
    AssignmentExpression: function(path) {
      var left = path.node.left;
      // Early return to flatten nesting
      if (left.type !== 'MemberExpression') return;
      var chain = getMemberChain(left);
      if (!chain) return;

      result.memberAssignments.push({
        obj: getMemberObjectName(left.object),
        prop: left.property ? (left.property.name || left.property.value || '') : '',
        full_chain: chain,
        line: path.node.loc ? path.node.loc.start.line : 0,
      });
    },
  });

  return result;
}


module.exports = { parseJS, createParseResult };
