/**
 * JS/TS AST Rules Engine - Node.js side
 * 
 * 煋鉴 v4.4 前端 AST 规则引擎入口
 * 基于 @babel/parser + @babel/traverse 实现深度语法分析
 * 
 * 模块结构：
 *   - js_ast_babel.js       Babel 依赖初始化（单例）
 *   - js_ast_utils.js       基础工具（位置/makeIssue/模式提取等纯函数）
 *   - js_ast_hook_utils.js  Hook 识别 + 闭包分析 + setter 收集
 *   - js_ast_analysis.js    分析辅助（复杂度判断等）
 *   - js_ast_rule_defs.js   规则元数据定义
 *   - js_ast_rules_runner.js 规则执行器（runRules 主函数）
 *   - js_ast_rules_engine.js 入口聚合
 * 
 * 协议：
 *   输入: { content: string, filename: string, ruleIds?: string[] }
 *   输出: { issues: [{ ruleId, message, line, col, endLine, endCol, severity, fix, snippet }] }
 */

const { runRules, RULES } = require('./js_ast_rules_runner.js');
const { isHookCall, getHookName, getDepArray,
        isReactFunctionComponent, isCustomHook } = require('./js_ast_hook_utils.js');

module.exports = {
  runRules,
  RULES,
  isHookCall,
  getHookName,
  getDepArray,
  isReactFunctionComponent,
  isCustomHook,
};
