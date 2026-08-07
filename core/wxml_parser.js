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



function parseWXML(content) {
  if (!htmlparser2) {
    return { error: 'htmlparser2 not available' };
  }

  var result = {
    tags: [],
    bindings: [],
    wxForTags: [],
    images: [],
    mustacheCount: { open: 0, close: 0 },
  };

  // Count mustache braces
  result.mustacheCount.open = (content.match(/\{\{/g) || []).length;
  result.mustacheCount.close = (content.match(/\}\}/g) || []).length;

  var parser = new htmlparser2.Parser({
    onopentag: function(name, attribs) {
      handleWxmlOpenTag(result, name, attribs, getLineAt(content, parser.startIndex));
    },

    onopentagname: function() {},
    onerror: function() {},
  }, {
    lowerCaseTags: false,
    lowerCaseAttributeNames: false,
    recognizeSelfClosing: true,
  });

  parser.write(content);
  parser.end();

  return result;
}


module.exports = { parseWXML };
