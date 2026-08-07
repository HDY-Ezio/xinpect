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


// 拆分后的模块
const helpers = require("./ast_helpers");
const { parseJS, createParseResult } = require("./js_parser");
const { parseWXML } = require("./wxml_parser");

// v4.4 JS/TS AST 规则引擎
let jsAstRulesEngine = null;
try {
  jsAstRulesEngine = require("./js_ast_rules_engine");
} catch (_astRulesErr) {
  jsAstRulesEngine = null;
}

// 导入helper函数到本地作用域
const isEmptyBody = helpers.isEmptyBody;
const getMemberChain = helpers.getMemberChain;
const getMemberObjectName = helpers.getMemberObjectName;
const hasTodoNearby = helpers.hasTodoNearby;
const getArrowFunctionName = helpers.getArrowFunctionName;
const analyzeCallee = helpers.analyzeCallee;
const extractSetDataKeys = helpers.extractSetDataKeys;
const getLineAt = helpers.getLineAt;
const getParentObjectName = helpers.getParentObjectName;
const extractBinding = helpers.extractBinding;
const copyAttribs = helpers.copyAttribs;
const makeWxmlRecord = helpers.makeWxmlRecord;
const handleWxmlOpenTag = helpers.handleWxmlOpenTag;

// ===== Main loop: read commands from stdin, write responses to stdout =====

var rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  terminal: false,
});

rl.on('line', function(line) {
  var response;
  try {
    var cmd = JSON.parse(line);

    if (cmd.type === 'js') {
      var data = parseJS(cmd.content || '', cmd.filename || '');
      response = data.error
        ? { id: cmd.id, ok: false, error: data.error }
        : { id: cmd.id, ok: true, data: data };
    } else if (cmd.type === 'wxml') {
      var data2 = parseWXML(cmd.content || '');
      response = data2.error
        ? { id: cmd.id, ok: false, error: data2.error }
        : { id: cmd.id, ok: true, data: data2 };
    } else if (cmd.type === 'js_ast_rules') {
      // v4.4: JS/TS AST 规则执行
      if (!jsAstRulesEngine) {
        response = { id: cmd.id, ok: false, error: 'JS AST rules engine not available' };
      } else {
        var result = jsAstRulesEngine.runRules(
          cmd.content || '',
          cmd.filename || '',
          cmd.ruleIds || []
        );
        response = result.error
          ? { id: cmd.id, ok: false, error: result.error }
          : { id: cmd.id, ok: true, data: result };
      }
    } else if (cmd.type === 'ping') {
      response = { id: cmd.id, ok: true, data: { pong: true, hasBabel: !!babelParser, hasHtmlparser2: !!htmlparser2 } };
    } else {
      response = { id: cmd.id, ok: false, error: 'Unknown type: ' + cmd.type };
    }
  } catch (e) {
    response = { ok: false, error: e.message };
  }

  process.stdout.write(JSON.stringify(response) + '\n');
});

// Signal ready
process.stdout.write(JSON.stringify({ id: 0, ok: true, data: { ready: true, hasBabel: !!babelParser, hasHtmlparser2: !!htmlparser2, hasAstRules: !!jsAstRulesEngine } }) + '\n');

