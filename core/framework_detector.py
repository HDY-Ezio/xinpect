"""
框架检测器 - QA框架P1阶段核心组件
识别项目使用的Web框架/技术栈，根据框架类型启用/禁用对应规则集

支持检测的框架:
- Python后端: Flask, Django, FastAPI, Tornado, SCF(云函数)
- 前端: React, Vue, Next.js, Nuxt.js
- 小程序: 微信原生, Taro, uni-app
- 桌面: Electron

使用方式:
    detector = FrameworkDetector(project_path, backend_path)
    framework = detector.detect()
    # framework = {
    #     'primary': 'flask',
    #     'frontend': 'react',
    #     'backend': 'flask',
    #     'features': ['flask_cors', 'flask_sqlalchemy'],
    #     'confidence': 0.9,
    # }
"""

import os
import re
from typing import Dict, List, Optional, Any


# 框架特征定义
FRAMEWORK_SIGNATURES = {
    # Python后端框架
    'flask': {
        'type': 'backend',
        'file_signatures': [],  # 无特定配置文件
        'import_patterns': [
            r'from\s+flask\s+import',
            r'import\s+flask',
            r'Flask\s*\(',
            r'@app\.route',
        ],
        'package_dependencies': ['flask', 'Flask'],
        'weight': 1.0,
    },
    'django': {
        'type': 'backend',
        'file_signatures': ['manage.py', 'settings.py', 'urls.py'],
        'import_patterns': [
            r'from\s+django',
            r'import\s+django',
            r'django\.',
        ],
        'package_dependencies': ['django', 'Django'],
        'weight': 1.0,
    },
    'fastapi': {
        'type': 'backend',
        'file_signatures': [],
        'import_patterns': [
            r'from\s+fastapi\s+import',
            r'import\s+fastapi',
            r'FastAPI\s*\(',
            r'@app\.(get|post|put|delete)',
        ],
        'package_dependencies': ['fastapi', 'FastAPI'],
        'weight': 1.0,
    },
    'tornado': {
        'type': 'backend',
        'file_signatures': [],
        'import_patterns': [
            r'from\s+tornado',
            r'import\s+tornado',
        ],
        'package_dependencies': ['tornado', 'Tornado'],
        'weight': 0.8,
    },
    'scf': {
        'type': 'backend',
        'file_signatures': [
            'template.yaml', 'template.yml',
            'serverless.yml', 'serverless.yaml',
        ],
        'import_patterns': [
            r'def\s+main_handler',
            r'def\s+handler\s*\(\s*event',
            r'SCF_TRIGGER',
            r'tencentcloud\.scf',
        ],
        'content_keywords': ['SCF', 'serverless', '云函数'],
        'weight': 0.7,
    },
    
    # 前端框架
    'react': {
        'type': 'frontend',
        'file_signatures': [],
        'import_patterns': [
            r'from\s+react',
            r'import\s+React',
            r'useState\s*\(',
            r'useEffect\s*\(',
        ],
        'package_dependencies': ['react', 'React'],
        'extension_hints': ['.jsx', '.tsx'],
        'weight': 0.9,
    },
    'vue': {
        'type': 'frontend',
        'file_signatures': ['vue.config.js', 'vue.config.ts', 'vite.config.ts'],
        'import_patterns': [
            r'from\s+vue',
            r'import\s+Vue',
            r'createApp\s*\(',
        ],
        'package_dependencies': ['vue', 'Vue'],
        'extension_hints': ['.vue'],
        'weight': 0.9,
    },
    'nextjs': {
        'type': 'frontend',
        'file_signatures': ['next.config.js', 'next.config.ts', 'next.config.mjs'],
        'import_patterns': [
            r'from\s+next/',
            r'next/head',
            r'next/router',
        ],
        'package_dependencies': ['next', 'Next.js'],
        'weight': 1.0,
    },
    'nuxt': {
        'type': 'frontend',
        'file_signatures': ['nuxt.config.js', 'nuxt.config.ts'],
        'import_patterns': [
            r'from\s+nuxt',
            r'nuxt/',
        ],
        'package_dependencies': ['nuxt', 'Nuxt.js'],
        'weight': 1.0,
    },
    
    # 小程序框架
    'wechat_miniprogram': {
        'type': 'miniprogram',
        'file_signatures': ['app.json', 'project.config.json'],
        'extension_hints': ['.wxml', '.wxss', '.wxs'],
        'weight': 1.0,
    },
    'taro': {
        'type': 'miniprogram',
        'file_signatures': ['config/index.js', 'config/dev.js', 'config/prod.js'],
        'import_patterns': [
            r'from\s+@tarojs',
            r'import\s+Taro',
        ],
        'package_dependencies': ['@tarojs/taro', 'taro'],
        'weight': 0.9,
    },
    'uniapp': {
        'type': 'miniprogram',
        'file_signatures': ['manifest.json', 'pages.json'],
        'import_patterns': [
            r'uni\.(request|navigateTo|showModal)',
        ],
        'package_dependencies': ['@dcloudio/uni-app', 'uni-app'],
        'weight': 0.9,
    },
    
    # 桌面框架
    'electron': {
        'type': 'desktop',
        'file_signatures': ['main.js', 'electron.js', 'main.ts'],
        'import_patterns': [
            r'from\s+electron',
            r'require\s*\(\s*["\']electron["\']',
            r'BrowserWindow',
            r'ipcMain',
            r'ipcRenderer',
        ],
        'package_dependencies': ['electron', 'Electron'],
        'weight': 1.0,
    },
    
    # 扣子技能/Agent
    'coze_skill': {
        'type': 'skill',
        'file_signatures': ['SKILL.md'],
        'weight': 1.0,
    },
}

# 框架特性（插件/中间件）检测
FEATURE_SIGNATURES = {
    'flask_cors': {
        'framework': 'flask',
        'patterns': [
            r'from\s+flask_cors\s+import',
            r'import\s+flask_cors',
            r'CORS\s*\(',
        ],
    },
    'flask_sqlalchemy': {
        'framework': 'flask',
        'patterns': [
            r'from\s+flask_sqlalchemy\s+import',
            r'import\s+flask_sqlalchemy',
            r'SQLAlchemy\s*\(',
            r'db\s*=\s*SQLAlchemy',
        ],
    },
    'flask_jwt': {
        'framework': 'flask',
        'patterns': [
            r'flask_jwt',
            r'flask_jwt_extended',
            r'jwt_required',
            r'create_access_token',
        ],
    },
    'flask_restful': {
        'framework': 'flask',
        'patterns': [
            r'from\s+flask_restful\s+import',
            r'flask_restful',
            r'add_resource',
        ],
    },
    'django_rest_framework': {
        'framework': 'django',
        'patterns': [
            r'rest_framework',
            r'from\s+rest_framework',
        ],
    },
    'pytest': {
        'framework': 'any',
        'patterns': [
            r'import\s+pytest',
            r'@pytest\.',
            r'def\s+test_',
        ],
    },
    'celery': {
        'framework': 'any',
        'patterns': [
            r'from\s+celery\s+import',
            r'import\s+celery',
            r'Celery\s*\(',
            r'@shared_task',
            r'@app\.task',
        ],
    },
    'redis': {
        'framework': 'any',
        'patterns': [
            r'import\s+redis',
            r'from\s+redis\s+import',
            r'Redis\s*\(',
            r'redis\.Redis',
        ],
    },
}


class FrameworkDetector:
    """框架检测器
    
    自动识别项目使用的技术栈和框架，用于：
    1. 启用/禁用对应规则集
    2. 选择合适的分析引擎（AST/正则等）
    3. 提供更精准的检查建议
    """
    
    def __init__(
        self,
        project_path: str = "",
        backend_path: str = "",
        config: dict = None,
    ):
        self.project_path = project_path
        self.backend_path = backend_path or project_path
        self.config = config or {}
        
        # 排除目录
        self.exclude_dirs = set(
            self.config.get("exclude_dirs", [])
            + ['node_modules', '__pycache__', '.git', 'venv', 'dist', 'build']
        )
        
        # 检测结果缓存
        self._result_cache = None
    
    def detect(self) -> Dict[str, Any]:
        """检测项目使用的框架
        
        Returns:
            框架检测结果字典:
            {
                'primary': 主框架名称,
                'backend': 后端框架,
                'frontend': 前端框架,
                'miniprogram': 小程序框架,
                'desktop': 桌面框架,
                'features': [特性列表],
                'confidence': 置信度 (0-1),
                'file_type_engines': {扩展名: 分析引擎类型},
            }
        """
        if self._result_cache is not None:
            return self._result_cache
        
        result = {
            'primary': 'unknown',
            'backend': 'unknown',
            'frontend': 'unknown',
            'miniprogram': 'unknown',
            'desktop': 'unknown',
            'skill': 'unknown',
            'features': [],
            'confidence': 0.0,
            'framework_scores': {},
            'file_type_engines': self._get_default_file_engines(),
        }
        
        # 收集所有相关文件
        all_files = self._collect_files()
        
        if not all_files:
            self._result_cache = result
            return result
        
        # 读取package.json（如果有）
        package_deps = self._read_package_json()
        
        # 读取requirements.txt / pyproject.toml（如果有）
        py_deps = self._read_python_deps()
        
        # 检测每个框架
        scores = {}
        for fw_name, fw_sig in FRAMEWORK_SIGNATURES.items():
            score = 0.0
            max_score = 0.0
            
            # 1. 文件签名检测（权重最高）
            if fw_sig.get('file_signatures'):
                max_score += 50
                for sig_file in fw_sig['file_signatures']:
                    if any(f.endswith(sig_file) for f in all_files):
                        score += 50
                        break
            
            # 2. 文件扩展名提示
            if fw_sig.get('extension_hints'):
                max_score += 20
                ext_count = 0
                for ext in fw_sig['extension_hints']:
                    ext_count += sum(1 for f in all_files if f.endswith(ext))
                if ext_count > 0:
                    score += min(20, ext_count * 2)
            
            # 3. import模式检测
            if fw_sig.get('import_patterns'):
                max_score += 30
                match_count = self._count_pattern_matches(
                    all_files, fw_sig['import_patterns']
                )
                if match_count > 0:
                    score += min(30, match_count * 5)
            
            # 4. 包依赖检测
            if fw_sig.get('package_dependencies'):
                max_score += 20
                deps = package_deps if fw_sig['type'] in ('frontend', 'desktop', 'miniprogram') else py_deps
                for dep in fw_sig['package_dependencies']:
                    if dep.lower() in (d.lower() for d in deps):
                        score += 20
                        break
            
            if max_score > 0:
                normalized_score = (score / max_score) * fw_sig.get('weight', 1.0)
                scores[fw_name] = normalized_score
        
        result['framework_scores'] = scores
        
        # 按类型分类，确定每个类型的主框架
        type_frameworks = {}
        for fw_name, fw_sig in FRAMEWORK_SIGNATURES.items():
            fw_type = fw_sig['type']
            if fw_name in scores and scores[fw_name] > 0.3:  # 阈值
                if fw_type not in type_frameworks or scores[fw_name] > type_frameworks[fw_type][1]:
                    type_frameworks[fw_type] = (fw_name, scores[fw_name])
        
        # 填充结果
        for fw_type, (fw_name, confidence) in type_frameworks.items():
            result[fw_type] = fw_name
            if confidence > result['confidence']:
                result['confidence'] = confidence
                result['primary'] = fw_name
        
        # 检测框架特性
        features = []
        for feat_name, feat_sig in FEATURE_SIGNATURES.items():
            # 只检测相关框架的特性
            fw = feat_sig.get('framework', 'any')
            if fw != 'any' and result.get(fw, 'unknown') != fw:
                # 框架不匹配，但如果有匹配模式也可以报告
                pass
            
            # 检查模式匹配
            match_count = self._count_pattern_matches(all_files, feat_sig['patterns'])
            if match_count > 0:
                features.append(feat_name)
        
        result['features'] = features
        
        # 确定文件类型对应的分析引擎
        result['file_type_engines'] = self._determine_file_engines(result)
        
        self._result_cache = result
        return result
    
    def get_applicable_rules(self, all_rules: list) -> list:
        """根据框架类型过滤适用的规则
        
        Args:
            all_rules: 所有规则列表
            
        Returns:
            适用的规则列表
        """
        framework_info = self.detect()
        primary = framework_info['primary']
        features = set(framework_info['features'])
        
        applicable = []
        for rule in all_rules:
            # 检查规则是否有框架限制
            rule_frameworks = getattr(rule, 'frameworks', None)
            if rule_frameworks:
                if primary not in rule_frameworks and not any(f in rule_frameworks for f in features):
                    continue
            applicable.append(rule)
        
        return applicable
    
    def get_file_engine(self, file_path: str) -> str:
        """获取文件对应的分析引擎
        
        Args:
            file_path: 文件路径
            
        Returns:
            引擎类型: 'ast' | 'regex' | 'ui_only' | 'skip'
        """
        framework_info = self.detect()
        engines = framework_info['file_type_engines']
        
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        return engines.get(ext, 'regex')
    
    def _collect_files(self) -> List[str]:
        """收集项目中的所有文件"""
        files = []
        search_paths = []
        
        if self.project_path and os.path.isdir(self.project_path):
            search_paths.append(self.project_path)
        if self.backend_path and self.backend_path != self.project_path and os.path.isdir(self.backend_path):
            search_paths.append(self.backend_path)
        
        for search_path in search_paths:
            for root, dirs, filenames in os.walk(search_path):
                dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
                for f in filenames:
                    files.append(os.path.join(root, f))
        
        return files
    
    def _read_package_json(self) -> List[str]:
        """读取package.json中的依赖"""
        deps = []
        search_paths = [self.project_path, self.backend_path]
        
        for base_path in search_paths:
            pkg_path = os.path.join(base_path, 'package.json')
            if os.path.isfile(pkg_path):
                try:
                    import json
                    with open(pkg_path, 'r', encoding='utf-8') as f:
                        pkg = json.load(f)
                    
                    for dep_section in ['dependencies', 'devDependencies']:
                        if dep_section in pkg:
                            deps.extend(pkg[dep_section].keys())
                except (json.JSONDecodeError, OSError):  # noqa: intentional empty handler
                    pass
        
        return list(set(deps))
    
    def _parse_requirements_file(self, path: str) -> List[str]:
        """Parse requirements.txt, extract package names."""
        deps = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pkg_name = re.split(r"[=<>!~]", line)[0].strip()
                        if pkg_name:
                            deps.append(pkg_name)
        except OSError:  # noqa: intentional empty handler
            pass
        return deps

    def _parse_pyproject_toml(self, path: str) -> List[str]:
        """Parse pyproject.toml, extract dependency names."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                toml_content = f.read()
            return re.findall(r'["\']([\w\-]+)[\'"]\s*=', toml_content)
        except OSError:
            return []

    def _read_python_deps(self) -> List[str]:
        """Read Python dependencies from requirements.txt and pyproject.toml."""
        deps = []
        search_paths = [self.project_path, self.backend_path]

        for base_path in search_paths:
            req_path = os.path.join(base_path, "requirements.txt")
            if os.path.isfile(req_path):
                deps.extend(self._parse_requirements_file(req_path))

            pyproject_path = os.path.join(base_path, "pyproject.toml")
            if os.path.isfile(pyproject_path):
                deps.extend(self._parse_pyproject_toml(pyproject_path))

        return list(set(deps))
    def _count_pattern_matches(self, files: List[str], patterns: List[str]) -> int:
        """统计模式匹配次数"""
        count = 0
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        
        # 只检查代码文件
        code_files = [
            f for f in files
            if f.endswith(('.py', '.js', '.ts', '.jsx', '.tsx', '.vue'))
        ]
        
        # 限制检查文件数量，避免性能问题
        max_files = 50
        for fpath in code_files[:max_files]:
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                
                for pattern in compiled_patterns:
                    if pattern.search(content):
                        count += 1
                        if count >= 10:  # 上限，够用就行
                            return count
            except OSError:
                continue
        
        return count
    
    def _get_default_file_engines(self) -> Dict[str, str]:
        """获取默认的文件分析引擎映射"""
        return {
            '.py': 'ast',      # Python文件用AST分析
            '.js': 'regex',    # JS文件用正则+语法提示
            '.jsx': 'regex',
            '.ts': 'regex',
            '.tsx': 'regex',
            '.wxml': 'ui_only',  # 小程序模板只跑UI规则
            '.wxss': 'ui_only',  # 小程序样式只跑UI规则
            '.wxs': 'regex',
            '.html': 'regex',
            '.css': 'ui_only',
            '.scss': 'ui_only',
            '.less': 'ui_only',
            '.vue': 'regex',
        }
    
    def _determine_file_engines(self, framework_info: dict) -> Dict[str, str]:
        """根据框架确定文件分析引擎"""
        engines = self._get_default_file_engines()
        
        primary = framework_info['primary']
        backend = framework_info.get('backend', 'unknown')
        
        # Python后端框架：.py文件优先用AST
        if backend in ('flask', 'django', 'fastapi', 'tornado', 'scf'):
            engines['.py'] = 'ast'
        
        # SCF项目：可能有很多配置文件，.py仍然用AST
        if primary == 'scf':
            engines['.py'] = 'ast'
            engines['.yaml'] = 'regex'
            engines['.yml'] = 'regex'
        
        return engines
    
    @property
    def is_flask(self) -> bool:
        """是否为Flask项目"""
        return self.detect()['backend'] == 'flask'
    
    @property
    def is_django(self) -> bool:
        """是否为Django项目"""
        return self.detect()['backend'] == 'django'
    
    @property
    def is_fastapi(self) -> bool:
        """是否为FastAPI项目"""
        return self.detect()['backend'] == 'fastapi'
    
    @property
    def is_react(self) -> bool:
        """是否为React项目"""
        return self.detect()['frontend'] == 'react'
    
    @property
    def is_vue(self) -> bool:
        """是否为Vue项目"""
        return self.detect()['frontend'] == 'vue'
    
    @property
    def is_miniprogram(self) -> bool:
        """是否为小程序项目"""
        return self.detect()['miniprogram'] != 'unknown'
    
    @property
    def is_skill(self) -> bool:
        """是否为扣子技能项目"""
        return self.detect()['skill'] != 'unknown'


# 全局单例
_detector = None


def get_framework_detector(
    project_path: str = "",
    backend_path: str = "",
    config: dict = None,
) -> FrameworkDetector:
    """获取框架检测器（全局单例，按路径缓存）"""
    global _detector
    if _detector is None:
        _detector = FrameworkDetector(project_path, backend_path, config)
    return _detector


def detect_framework(
    project_path: str = "",
    backend_path: str = "",
    config: dict = None,
) -> Dict[str, Any]:
    """便捷API：检测项目框架"""
    detector = FrameworkDetector(project_path, backend_path, config)
    return detector.detect()
