"""
测试与CI规则集
检查测试配置、CI/CD配置、代码规范配置等
"""

import os
import re
from typing import List, Dict, Any


def _get_search_dirs(context):
    """获取搜索目录"""
    root = context.project_root
    dirs = [root]
    for d in ['src', 'lib', 'app', 'pages']:
        p = os.path.join(root, d)
        if os.path.isdir(p):
            dirs.append(p)
    return dirs


def check_14_1_test_files(context) -> List[Dict]:
    """14.1 测试文件存在性"""
    results = []
    root = context.project_root
    test_patterns = ['**/__tests__/**', '**/*.test.*', '**/*.spec.*', '**/test/**', '**/tests/**']
    has_tests = False
    for pattern in test_patterns:
        if context.find_files_by_glob(pattern):
            has_tests = True
            break
    if not has_tests:
        src_files = context.find_files(['.js', '.ts', '.py', '.java', '.go'])
        if len(src_files) > 5:
            results.append({
                'id': '14.1', 'name': '测试文件存在性', 'level': 'suggestion',
                'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
                'description': '项目有源代码文件但未发现测试文件',
                'check': check_14_1_test_files,
            })
    return results


def check_14_2_coverage_config(context) -> List[Dict]:
    """14.2 测试覆盖率配置"""
    results = []
    root = context.project_root
    coverage_files = ['jest.config.*', '.nycrc', 'coverage.xml', '.coveragerc',
                      'nyc.config.*', 'vitest.config.*', 'pytest.ini']
    has_coverage = False
    for pattern in coverage_files:
        if context.find_files_by_glob(pattern):
            has_coverage = True
            break
    pkg = context.safe_read(os.path.join(root, 'package.json'))
    if pkg and 'jest' in pkg:
        has_coverage = True
    if not has_coverage:
        test_files = context.find_files_by_glob('**/*.test.*')
        if test_files:
            results.append({
                'id': '14.2', 'name': '测试覆盖率配置', 'level': 'suggestion',
                'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
                'description': '有测试文件但未配置覆盖率收集工具',
                'check': check_14_2_coverage_config,
            })
    return results


def check_14_3_ci_config(context) -> List[Dict]:
    """14.3 CI/CD配置"""
    results = []
    root = context.project_root
    ci_patterns = ['.github/workflows/*.yml', '.gitlab-ci.yml', 'Jenkinsfile',
                   '.circleci/config.yml', 'azure-pipelines.yml', 'bitbucket-pipelines.yml']
    has_ci = False
    for pattern in ci_patterns:
        if context.find_files_by_glob(pattern):
            has_ci = True
            break
    if not has_ci:
        git_dir = os.path.join(root, '.git')
        if os.path.isdir(git_dir):
            results.append({
                'id': '14.3', 'name': 'CI/CD配置', 'level': 'suggestion',
                'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
                'description': '项目使用Git但未配置CI/CD流水线',
                'check': check_14_3_ci_config,
            })
    return results


def check_14_4_lint_config(context) -> List[Dict]:
    """14.4 代码规范配置"""
    results = []
    root = context.project_root
    lint_files = {
        'python': ['.pylintrc', 'pyproject.toml', 'setup.cfg', '.flake8', 'ruff.toml'],
        'js': ['.eslintrc.js', '.eslintrc.json', '.eslintrc.yml', '.eslintrc', '.eslint.config.*'],
        'go': ['.golangci.yml', '.golangci.yaml'],
    }
    has_lint = False
    for lang, files in lint_files.items():
        for f in files:
            if context.find_files_by_glob(f'**/{f}'):
                has_lint = True
                break
        if has_lint:
            break
    pkg = context.safe_read(os.path.join(root, 'package.json'))
    if pkg and ('eslint' in pkg or 'prettier' in pkg):
        has_lint = True
    if not has_lint:
        results.append({
            'id': '14.4', 'name': '代码规范配置', 'level': 'suggestion',
            'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
            'description': '未配置代码规范检查工具(ESLint/Pylint/Ruff等)',
            'check': check_14_4_lint_config,
        })
    return results


def check_14_6_docs(context) -> List[Dict]:
    """14.6 文档完整性"""
    results = []
    root = context.project_root
    doc_files = ['README.md', 'README.rst', 'README.txt', 'readme.md']
    has_readme = any(os.path.exists(os.path.join(root, f)) for f in doc_files)
    if not has_readme:
        results.append({
            'id': '14.6', 'name': '文档完整性', 'level': 'suggestion',
            'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
            'description': '项目缺少README文档',
            'check': check_14_6_docs,
        })
    return results


RULES = [
    {
        'id': '14.1', 'name': '测试文件存在性', 'level': 'suggestion',
        'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
        'description': '项目有源代码文件但未发现测试文件',
        'check': check_14_1_test_files,
    },
    {
        'id': '14.2', 'name': '测试覆盖率配置', 'level': 'suggestion',
        'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
        'description': '有测试文件但未配置覆盖率收集工具',
        'check': check_14_2_coverage_config,
    },
    {
        'id': '14.3', 'name': 'CI/CD配置', 'level': 'suggestion',
        'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
        'description': '项目使用Git但未配置CI/CD流水线',
        'check': check_14_3_ci_config,
    },
    {
        'id': '14.4', 'name': '代码规范配置', 'level': 'suggestion',
        'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
        'description': '未配置代码规范检查工具(ESLint/Pylint/Ruff等)',
        'check': check_14_4_lint_config,
    },
    {
        'id': '14.6', 'name': '文档完整性', 'level': 'suggestion',
        'category': 'test_ci', 'module_id': '14', 'applicable_types': [],
        'description': '项目缺少README文档',
        'check': check_14_6_docs,
    },
]
