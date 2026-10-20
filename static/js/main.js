// CSRF token 自动附加
const _origFetch = window.fetch;
window.fetch = function(url, options = {}) {
    if (['POST', 'PUT', 'DELETE'].includes((options.method || 'GET').toUpperCase())) {
        options.headers = options.headers || {};
        if (options.headers instanceof Headers) {
            if (!options.headers.has('X-CSRF-Token')) {
                const meta = document.querySelector('meta[name="csrf-token"]');
                if (meta) options.headers.set('X-CSRF-Token', meta.content);
            }
        } else {
            if (!options.headers['X-CSRF-Token'] && !options.headers['x-csrf-token']) {
                const meta = document.querySelector('meta[name="csrf-token"]');
                if (meta) options.headers['X-CSRF-Token'] = meta.content;
            }
        }
        // Also add X-Requested-With for AJAX identification
        if (options.headers instanceof Headers) {
            if (!options.headers.has('X-Requested-With')) options.headers.set('X-Requested-With', 'XMLHttpRequest');
        } else {
            if (!options.headers['X-Requested-With']) options.headers['X-Requested-With'] = 'XMLHttpRequest';
        }
    }
    return _origFetch.call(this, url, options);
};

/* jshint -W117 */
/* eslint-disable no-undef */
// ============================================================
// 煋鉴 Xinpect - 主 JavaScript 文件
// 原生 JS，不依赖任何框架
// ============================================================

(function() {
    'use strict';

    // ---------- 通用工具函数 ----------
    /** @param {string} selector @param {Document|Element} [context] */
    function $(selector, context) {
        /* declared params: selector, context */
        var ctx = context || document;
        return ctx.querySelector(selector);
    }

    /** @param {string} selector @param {Document|Element} [context] */
    function $$(selector, context) {
        /* declared params: selector, context */
        var ctx = context || document;
        return Array.from(ctx.querySelectorAll(selector));
    }

    /** @param {number} bytes */
    function formatFileSize(bytes) {
        /* declared param: bytes */
        if (bytes < 1024) return String(bytes) + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';  // explicit string concat
        return (bytes / (1024 * 1024)).toFixed(2) + ' MB';  // explicit string concat
    }

    /** @param {string} text @returns {string} XSS安全的HTML转义 */
    function escapeHtml(text) {
        /* declared param: text */
        var div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;  // safe: textContent设置后读取，自动转义HTML
    }

    // 千分位分隔符
    /** @param {number|string|null} num @returns {string} */
    function formatNumber(num) {
        /* declared param: num */
        if (num === null || num === undefined || isNaN(num)) return '0';
        return Number(num).toLocaleString('en-US');
    }

    // ---------- 通用弹窗 (积分系统 v1.5) ----------
    /** @param {{cost: number, totalLines: number, onConfirm: Function, onCancel: Function}} options */
    function showCreditConfirmModal(options) {
        /* declared param: options */
        var cost = (options && options.cost) || 0;
        var totalLines = (options && options.totalLines) || 0;
        var html = '<div class="credit-modal-overlay" id="credit-confirm-modal">' +
            '<div class="credit-modal">' +
                '<div class="credit-modal-header">' +
                    '<div class="credit-modal-icon">⚡</div>' +
                    '<div class="credit-modal-title">确认开始扫描</div>' +
                    '<div class="credit-modal-desc">扫描需要消耗积分，请确认后继续</div>' +
                '</div>' +
                '<div class="credit-modal-cost">' +
                    '<div class="cost-value">' + formatNumber(cost) + '<span class="cost-unit">积分</span></div>' +
                    '<div class="cost-detail">约 ' + formatNumber(totalLines) + ' 行代码</div>' +
                '</div>' +
                '<div class="credit-modal-hint">积分按代码行数计算，包含起步费10积分 + 按行计费</div>' +
                '<div class="credit-modal-actions">' +
                    '<button class="btn btn-secondary" id="confirm-cancel-btn">取消</button>' +
                    '<button class="btn btn-orange" id="confirm-ok-btn">确认扫描</button>' +
                '</div>' +
            '</div>' +
        '</div>';
        document.body.insertAdjacentHTML('beforeend', html);  // html由静态模板+数字格式化的安全拼接构成

        var modal = document.getElementById('credit-confirm-modal');
        document.getElementById('confirm-cancel-btn').addEventListener('click', function() {
            modal.remove();
            if (options.onCancel) options.onCancel();
        });
        document.getElementById('confirm-ok-btn').addEventListener('click', function() {
            modal.remove();
            if (options.onConfirm) options.onConfirm();
        });
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.remove();
                if (options.onCancel) options.onCancel();
            }
        });
    }

    function showCreditInsufficientModal(options) {
        // options: { currentCredits, needCredits, onBuyPack, onUpgrade }
        var current = options.currentCredits || 0;
        var need = options.needCredits || 0;
        var html = '<div class="credit-modal-overlay" id="credit-insufficient-modal">' +
            '<div class="credit-modal credit-insufficient">' +
                '<div class="credit-modal-header">' +
                    '<div class="credit-modal-icon">⚠️</div>' +
                    '<div class="credit-modal-title">积分不足</div>' +
                    '<div class="credit-modal-desc">当前积分不足以完成本次扫描</div>' +
                '</div>' +
                '<div class="credit-modal-cost">' +
                    '<div class="credit-compare-row">' +
                        '<span class="label">当前积分</span>' +
                        '<span class="value current">' + formatNumber(current) + '</span>' +
                    '</div>' +
                    '<div class="credit-compare-row">' +
                        '<span class="label">本次需要</span>' +
                        '<span class="value need">' + formatNumber(need) + '</span>' +
                    '</div>' +
                '</div>' +
                '<div class="credit-modal-actions">' +
                    '<button class="btn btn-secondary" id="insufficient-upgrade-btn">升级会员</button>' +
                    '<button class="btn btn-orange" id="insufficient-pack-btn">购买积分包</button>' +
                '</div>' +
            '</div>' +
        '</div>';
        document.body.insertAdjacentHTML('beforeend', html);  // html由静态模板+数字格式化的安全拼接构成

        var modal = document.getElementById('credit-insufficient-modal');
        document.getElementById('insufficient-upgrade-btn').addEventListener('click', function() {
            modal.remove();
            if (options.onUpgrade) options.onUpgrade();
        });
        document.getElementById('insufficient-pack-btn').addEventListener('click', function() {
            modal.remove();
            if (options.onBuyPack) options.onBuyPack();
        });
        modal.addEventListener('click', function(e) {
            if (e.target === modal) modal.remove();
        });
    }

    // 暴露积分相关全局函数
    window.XinpectCredit = {
        formatNumber: formatNumber,
        showCreditConfirmModal: showCreditConfirmModal,
        showCreditInsufficientModal: showCreditInsufficientModal
    };

    // ---------- 导航栏交互 ----------
    function initNavbar() {
        // 滚动时添加阴影
        var navbar = $('.navbar');
        if (!navbar) return;

        window.addEventListener('scroll', function() {
            if (window.scrollY > 10) {
                navbar.style.boxShadow = '0 2px 20px rgba(0,0,0,0.3)';
            } else {
                navbar.style.boxShadow = 'none';
            }
        });
    }

    // ---------- 上传功能 ----------
    var uploadState = {
        files: [],     // File 对象数组
        codeText: '',  // 粘贴的代码
        mode: 'file'   // file | code
    };

    function initUpload() {
        var uploadArea = $('#upload-area');
        if (!uploadArea) return;

        var fileInput = $('#file-input');
        var fileList = $('#file-list');
        var codeTab = $('#tab-code');
        var fileTab = $('#tab-file');
        var fileContent = $('#tab-content-file');
        var codeContent = $('#tab-content-code');
        var codeTextarea = $('#code-textarea');
        var fileNameInput = $('#code-filename');
        var scanBtn = $('#scan-btn');

        // Tab 切换
        if (fileTab && codeTab) {
            fileTab.addEventListener('click', function() {
                uploadState.mode = 'file';
                fileTab.classList.add('active');
                codeTab.classList.remove('active');
                fileContent.classList.add('active');
                codeContent.classList.remove('active');
                updateScanButton();
            });

            codeTab.addEventListener('click', function() {
                uploadState.mode = 'code';
                codeTab.classList.add('active');
                fileTab.classList.remove('active');
                codeContent.classList.add('active');
                fileContent.classList.remove('active');
                updateScanButton();
            });
        }

        // 点击上传区域触发文件选择
        uploadArea.addEventListener('click', function(e) {
            if (uploadState.mode === 'file' && e.target.closest('.file-list') === null) {
                fileInput && fileInput.click();
            }
        });

        // 文件选择
        if (fileInput) {
            fileInput.addEventListener('change', function(e) {
                handleFiles(e.target.files);
                // 重置 input 以便能重复选择相同文件
                fileInput.value = '';
            });
        }

        // 拖拽上传
        ['dragenter', 'dragover'].forEach(function(eventName) {
            uploadArea.addEventListener(eventName, function(e) {
                e.preventDefault();
                e.stopPropagation();
                uploadArea.classList.add('dragover');
            });
        });

        ['dragleave', 'drop'].forEach(function(eventName) {
            uploadArea.addEventListener(eventName, function(e) {
                e.preventDefault();
                e.stopPropagation();
                uploadArea.classList.remove('dragover');
            });
        });

        uploadArea.addEventListener('drop', function(e) {
            if (uploadState.mode === 'file' && e.dataTransfer.files.length > 0) {
                handleFiles(e.dataTransfer.files);
            }
        });

        // 代码粘贴
        if (codeTextarea) {
            codeTextarea.addEventListener('input', function() {
                uploadState.codeText = codeTextarea.value;
                updateScanButton();
            });
        }

        // 开始检测
        if (scanBtn) {
            scanBtn.addEventListener('click', startScan);
        }

        function handleFiles(fileListObj) {
            var maxSize = 5 * 1024 * 1024; // 单文件 5MB
            var totalMax = 20 * 1024 * 1024; // 批量 20MB
            var totalSize = uploadState.files.reduce(function(sum, f) { return sum + f.size; }, 0);

            for (var i = 0; i < fileListObj.length; i++) {
                var file = fileListObj[i];
                if (file.size > maxSize) {
                    showFlash('文件 "' + file.name + '" 超过 5MB 限制', 'error');
                    continue;
                }
                if (totalSize + file.size > totalMax) {
                    showFlash('上传文件总大小超过 20MB 限制', 'error');
                    break;
                }
                uploadState.files.push(file);
                totalSize += file.size;
            }

            renderFileList();
            updateScanButton();
        }

        function renderFileList() {
            if (!fileList) return;

            if (uploadState.files.length === 0) {
                fileList.innerHTML = '';
                return;
            }

            var html = '';
            uploadState.files.forEach(function(file, index) {
                html += '<div class="file-item">' +
                    '<div class="file-item-name">' +
                    '<span>📄</span>' +
                    '<span>' + escapeHtml(file.name) + '</span>' +
                    '</div>' +
                    '<span class="file-item-size">' + formatFileSize(file.size) + '</span>' +
                    '<button class="file-item-remove" data-index="' + index + '" title="移除">✕</button>' +
                    '</div>';
            });
            fileList.innerHTML = html;

            // 绑定移除事件
            $$('.file-item-remove', fileList).forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    var idx = parseInt(btn.getAttribute('data-index'));
                    uploadState.files.splice(idx, 1);
                    renderFileList();
                    updateScanButton();
                });
            });
        }

        function updateScanButton() {
            if (!scanBtn) return;
            var canScan = false;
            if (uploadState.mode === 'file') {
                canScan = uploadState.files.length > 0;
            } else {
                canScan = uploadState.codeText.trim().length > 0;
            }
            scanBtn.disabled = !canScan;
        }

        function startScan() {
            if (scanBtn.disabled) return;

            scanBtn.disabled = true;
            scanBtn.textContent = '检测中...';

            var formData = new FormData();
            formData.append('language', $('#language-select') ? $('#language-select').value : 'auto');

            if (uploadState.mode === 'file') {
                uploadState.files.forEach(function(file) {
                    formData.append('files', file, file.name);
                });
            } else {
                formData.append('code', uploadState.codeText);
                formData.append('filename', fileNameInput ? fileNameInput.value || 'code.txt' : 'code.txt');
            }

            // 显示进度
            var progressSection = $('#scan-progress');
            var uploadSection = $('#upload-form');
            if (progressSection && uploadSection) {
                uploadSection.style.display = 'none';
                progressSection.style.display = 'block';
            }

            var progressBar = $('.progress-bar-fill');
            var progressText = $('#progress-text');
            var progress = 0;
            var progressInterval = setInterval(function() {
                progress += Math.random() * 15;
                if (progress > 85) progress = 85;
                if (progressBar) progressBar.style.width = progress + '%';
            }, 500);

            fetch('/scan', {
                method: 'POST',
                body: formData
            }).then(function(response) {
                return response.json().then(function(data) {
                    if (!response.ok) throw new Error(data.error || '检测失败');
                    return data;
                });
            }).then(function(data) {
                clearInterval(progressInterval);
                if (progressBar) progressBar.style.width = '100%';
                if (progressText) progressText.textContent = '检测完成，正在跳转...';
                setTimeout(function() {
                    window.location.href = '/report/' + data.scan_id;
                }, 500);
            }).catch(function(error) {
                clearInterval(progressInterval);
                scanBtn.disabled = false;
                scanBtn.textContent = '开始检测';
                if (progressSection && uploadSection) {
                    progressSection.style.display = 'none';
                    uploadSection.style.display = 'block';
                }
                showFlash(error.message || '检测失败，请重试', 'error');
            });
        }
    }

    // ---------- 报告页交互 ----------
    var currentTier = 'all';
        var currentSource = 'all';  // 检测方式筛选: all / rule / ai
    var tierNames = {spec: '规范层', quality: '质量层', security: '防护层'};
    var brainNames = {
        '1': '语法与AST分析',
        '2': '安全检测',
        '3': '性能与可靠性',
        '4': '代码质量与可观测性',
        '5': '架构与部署',
        '6': '组件合规',
        '7': 'AI智能扫描',
        '8': '业务安全',
        '9': '组件合规',
        '10': '安全检测'
    };
    var B2E = {'1':'1','2':'2','3':'1','4':'3','5':'4','6':'4','7':'5','8':'2','9':'6','10':'2'};
    
    function initReport() {
        // 三层卡片点击筛选
        $$('.tier-mini-card').forEach(function(card) {
            card.addEventListener('click', function() {
                var tierKey = card.getAttribute('data-tier');
                if (currentTier === tierKey) {
                    // 取消筛选 → 全部
                    currentTier = 'all';
                    $$('.tier-mini-card').forEach(function(c) { c.classList.remove('tier-active'); });
                    var tag = document.getElementById('tier-filter-tag');
                    if (tag) tag.style.display = 'none';
                    updateResetButton();
                } else {
                    // 选中某层
                    currentTier = tierKey;
                    $$('.tier-mini-card').forEach(function(c) { c.classList.remove('tier-active'); });
                    card.classList.add('tier-active');
                    var tag = document.getElementById('tier-filter-tag');
                    if (tag) {
                        tag.style.display = 'inline-block';
                        tag.textContent = tierNames[tierKey];
                    }
                    // 重置引擎筛选为"全部"（避免叠加过滤）
                    $$('.dimension-card').forEach(function(c) { c.classList.remove('active'); });
                    updateBrainFilterTag();
                    updateResetButton();
                    // 滚动到问题列表
                    var issuesSection = document.querySelector('.issues-section');
                    if (issuesSection) issuesSection.scrollIntoView({behavior: 'smooth', block: 'start'});
                }
                updateIssueDisplay();
            });
        });
        
        // 维度卡片点击筛选
        $$('.dimension-card:not(.locked)').forEach(function(card) {
            card.addEventListener('click', function() {
                var brainId = card.getAttribute('data-brain');
                filterByBrain(brainId);
            });
        });

        // 严重程度筛选
        $$('.filter-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var severity = btn.getAttribute('data-filter');
                filterBySeverity(severity);
            });
        });

        // 检测方式筛选（规则 / AI）
        $$('.source-filter-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var source = btn.getAttribute('data-source');
                filterBySource(source);
            });
        });

        // 问题展开/折叠
        $$('.issue-item .issue-header').forEach(function(header) {
            header.addEventListener('click', function() {
                var item = header.parentElement;
                item.classList.toggle('expanded');
            });
        });

        // 得分动画
        var scoreFill = $('.report-score-circle .score-fill');
        var scoreNumber = $('.report-score-number');
        if (scoreFill && scoreNumber) {
            var score = parseFloat(scoreNumber.textContent);
            var circumference = 2 * Math.PI * 60; // r=60
            var offset = circumference - (score / 100) * circumference;

            // 延迟执行动画
            setTimeout(function() {
                scoreFill.style.strokeDashoffset = offset;
            }, 200);
        }

        function filterByBrain(brainId) {
            $$('.dimension-card').forEach(function(card) {
                card.classList.remove('active');
            });
            var activeCard = document.querySelector('.dimension-card[data-brain="' + brainId + '"]');
            if (activeCard) activeCard.classList.add('active');
            // 重置三层筛选为"全部"（避免叠加过滤）
            currentTier = 'all';
            $$('.tier-mini-card').forEach(function(c) { c.classList.remove('tier-active'); });
            var tag = document.getElementById('tier-filter-tag');
            if (tag) tag.style.display = 'none';
            updateBrainFilterTag();
            updateResetButton();
            updateIssueDisplay();
            // 滚动到问题列表
            var issuesSection = document.querySelector('.issues-section');
            if (issuesSection) issuesSection.scrollIntoView({behavior: 'smooth', block: 'start'});
        }
        window.filterByBrain = filterByBrain;

        function filterBySeverity(severity) {
            $$('.filter-btn').forEach(function(btn) {
                btn.classList.remove('active');
            });
            var activeBtn = document.querySelector('.filter-btn[data-filter="' + severity + '"]');
            if (activeBtn) activeBtn.classList.add('active');
            updateIssueDisplay();
        }

        function filterBySource(source) {
            currentSource = source;
            $$('.source-filter-btn').forEach(function(btn) {
                btn.classList.remove('source-active');
            });
            var activeBtn = document.querySelector('.source-filter-btn[data-source="' + source + '"]');
            if (activeBtn) activeBtn.classList.add('source-active');
            updateResetButton();
            updateIssueDisplay();
        }

        function updateBrainFilterTag() {
            var activeBrain = document.querySelector('.dimension-card.active:not(.locked)');
            var tag = document.getElementById('brain-filter-tag');
            if (!tag) return;
            if (activeBrain) {
                var brainId = activeBrain.getAttribute('data-brain');
                tag.textContent = brainNames[brainId] || ('E' + (B2E[brainId] || brainId));
                tag.style.display = 'inline-block';
            } else {
                tag.style.display = 'none';
            }
        }

        function updateResetButton() {
            var btn = document.getElementById('reset-all-filter');
            if (!btn) return;
            var hasTierFilter = (currentTier !== 'all');
            var hasBrainFilter = !!document.querySelector('.dimension-card.active:not(.locked)');
            var hasSourceFilter = (currentSource !== 'all');
            if (hasTierFilter || hasBrainFilter || hasSourceFilter) {
                btn.style.display = 'inline-block';
            } else {
                btn.style.display = 'none';
            }
        }

        function resetAllFilters() {
            // 重置检测方式
            currentSource = 'all';
            $$('.source-filter-btn').forEach(function(btn) { btn.classList.remove('source-active'); });
            var srcAllBtn = document.querySelector('.source-filter-btn[data-source="all"]');
            if (srcAllBtn) srcAllBtn.classList.add('source-active');
            // 重置三层
            currentTier = 'all';
            $$('.tier-mini-card').forEach(function(c) { c.classList.remove('tier-active'); });
            var tierTag = document.getElementById('tier-filter-tag');
            if (tierTag) tierTag.style.display = 'none';
            // 重置引擎
            $$('.dimension-card').forEach(function(c) { c.classList.remove('active'); });
            var brainTag = document.getElementById('brain-filter-tag');
            if (brainTag) brainTag.style.display = 'none';
            // 重置严重度
            filterBySeverity('all');
            updateResetButton();
            updateIssueDisplay();
        }
        window.resetAllFilters = resetAllFilters;

        function updateIssueDisplay() {
            var activeBrain = document.querySelector('.dimension-card.active:not(.locked)');
            var brainFilter = activeBrain ? activeBrain.getAttribute('data-brain') : 'all';
            var sevFilter = document.querySelector('.filter-btn.active')?.getAttribute('data-filter') || 'all';
            var visible = 0;
            
            $$('.issue-item').forEach(function(item) {
                var itemBrain = item.getAttribute('data-brain');
                var itemSev = item.getAttribute('data-severity');
                var itemTier = item.getAttribute('data-tier');
                var itemSource = item.getAttribute('data-source') || 'rule';
                
                var matchBrain = (brainFilter === 'all' || itemBrain === brainFilter);
                var matchSev = (sevFilter === 'all' || itemSev === sevFilter);
                var matchTier = (currentTier === 'all' || itemTier === currentTier);
                var matchSource = (currentSource === 'all' || itemSource === currentSource);
                
                if (matchBrain && matchSev && matchTier && matchSource) {
                    item.style.display = '';
                    visible++;
                } else {
                    item.style.display = 'none';
                }
            });
            
            document.getElementById('issues-count').textContent = '(' + visible + ')';
        }

        function updateVisibleIssuesCount() {
            var count = $$('.issue-item').filter(function(item) {
                return item.style.display !== 'none';
            }).length;
            var countEl = $('#issues-count');
            if (countEl) {
                countEl.textContent = count;
            }
        }

        // 下载报告
        var downloadBtn = $('#download-report');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', function() {
                var scanId = downloadBtn.getAttribute('data-scan-id');
                window.location.href = '/report/' + scanId + '/download';
            });
        }
    }

    // ---------- 充值页面 ----------
    function initRecharge() {
        $$('.recharge-plan').forEach(function(plan) {
            plan.addEventListener('click', function() {
                $$('.recharge-plan').forEach(function(p) { p.classList.remove('selected'); });
                plan.classList.add('selected');

                var planId = plan.getAttribute('data-plan');
                var payBtn = $('#pay-btn');
                if (payBtn) {
                    payBtn.disabled = false;
                    payBtn.setAttribute('data-plan', planId);
                }
            });
        });

        var payBtn = $('#pay-btn');
        if (payBtn) {
            payBtn.addEventListener('click', function() {
                var planId = payBtn.getAttribute('data-plan');
                if (!planId) return;

                // 调用创建订单接口
                fetch('/api/pay/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ plan_id: planId })
                }).then(function(response) {
                    return response.json();
                }).then(function(data) {
                    if (data.success) {
                        showPaymentModal(data.order_id, data.qr_url, data.amount);
                    } else {
                        showFlash(data.error || '创建订单失败', 'error');
                    }
                }).catch(function() {
                    showFlash('创建订单失败，请重试', 'error');
                });
            });
        }

        function showPaymentModal(orderId, qrUrl, amount) {
            // XSS防护：对用户可控数据做转义
            var safeAmount = escapeHtml(String(amount || 0));
            var safeQrUrl = qrUrl ? escapeHtml(qrUrl) : '';
            var modalHtml = '<div id="pay-modal" style="position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:1000;">' +
                '<div class="payment-modal">' +
                '<h3 style="font-size:18px;margin-bottom:8px;">扫码支付</h3>' +
                '<p style="color:var(--text-secondary);font-size:14px;margin-bottom:16px;">支付金额：<strong style="color:var(--accent-orange);font-size:24px;">¥' + safeAmount + '</strong></p>' +
                '<div class="qr-code">' +
                (safeQrUrl ? '<img src="' + safeQrUrl + '" alt="支付二维码" style="width:100%;height:100%;">' : '二维码生成中...') +
                '</div>' +
                '<p style="font-size:13px;color:var(--text-muted);margin-top:12px;">请使用微信扫码支付</p>' +
                '<p id="pay-status" style="font-size:13px;color:var(--warning);margin-top:8px;">等待支付中...</p>' +
                '<button class="btn btn-ghost btn-block" style="margin-top:16px;" onclick="this.closest(\'#pay-modal\').remove()">关闭</button>' +
                '</div></div>';

            document.body.insertAdjacentHTML('beforeend', modalHtml);

            // 轮询支付状态
            var statusEl = document.getElementById('pay-status');
            var pollCount = 0;
            var maxPolls = 60; // 最多轮询5分钟

            var pollInterval = setInterval(function() {
                pollCount++;
                if (pollCount > maxPolls) {
                    clearInterval(pollInterval);
                    if (statusEl) {
                        statusEl.textContent = '支付超时，请重新发起';
                        statusEl.style.color = 'var(--danger)';
                    }
                    return;
                }

                fetch('/api/pay/status/' + encodeURIComponent(orderId))
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (data.status === 'paid') {
                            clearInterval(pollInterval);
                            if (statusEl) {
                                statusEl.textContent = '✓ 支付成功！即将刷新...';
                                statusEl.style.color = 'var(--success)';
                            }
                            setTimeout(function() {
                                window.location.reload();
                            }, 1500);
                        } else if (data.status === 'expired') {
                            clearInterval(pollInterval);
                            if (statusEl) {
                                statusEl.textContent = '订单已过期';
                                statusEl.style.color = 'var(--danger)';
                            }
                        }
                    }).catch(function() { /* 网络异常静默处理 */ });
            }, 5000);
        }
    }

    // ---------- Flash 消息 ----------
    function showFlash(message, type) {
        type = type || 'info';
        var container = $('#flash-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'flash-container';
            container.style.cssText = 'position:fixed;top:80px;left:50%;transform:translateX(-50%);z-index:200;min-width:280px;';
            document.body.appendChild(container);
        }

        var msg = document.createElement('div');
        msg.className = 'flash-message ' + type;
        msg.textContent = message;
        msg.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
        container.appendChild(msg);

        setTimeout(function() {
            msg.style.opacity = '0';
            msg.style.transform = 'translateY(-10px)';
            msg.style.transition = 'all 0.3s ease';
            setTimeout(function() { msg.remove(); }, 300);
        }, 3000);
    }

    // 暴露全局函数
    window.Xinpect = {
        showFlash: showFlash
    };

    // ---------- 复制 AI 修复代码 ----------
    function copyFixCode(btn) {
        var fixBlock = btn.closest('.ai-fix-block');
        if (!fixBlock) return;

        var fixContent = fixBlock.querySelector('.ai-fix-content');
        if (!fixContent) return;

        // 提取代码块内容
        var codeBlock = fixContent.querySelector('pre');
        var text = codeBlock ? codeBlock.textContent : fixContent.textContent;

        navigator.clipboard.writeText(text).then(function() {
            var originalText = btn.textContent;
            btn.textContent = '✅ 已复制';
            btn.style.background = 'var(--success)';
            btn.style.borderColor = 'var(--success)';
            btn.style.color = '#fff';
            setTimeout(function() {
                btn.textContent = originalText;
                btn.style.background = '';
                btn.style.borderColor = '';
                btn.style.color = '';
            }, 2000);
        }).catch(function() {
            // fallback
            var textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            btn.textContent = '✅ 已复制';
            setTimeout(function() { btn.textContent = '📋 复制代码'; }, 2000);
        });
    }

    // 暴露到全局供 onclick 使用
    window.copyFixCode = copyFixCode;

    // ---------- 初始化 ----------
    document.addEventListener('DOMContentLoaded', function() {
        initNavbar();
        initUpload();
        initReport();
        initRecharge();

        // 自动淡出 flash 消息
        $$('.flash-message').forEach(function(msg) {
            setTimeout(function() {
                msg.style.opacity = '0';
                msg.style.transition = 'opacity 0.5s ease';
                setTimeout(function() { msg.remove(); }, 500);
            }, 4000);
        });
    });

})();


// ============================================================
// 全局错误监控 - 自动捕获并上报前端错误
// ============================================================
(function() {
    'use strict';
    
    var REPORT_URL = '/api/report-error';
    var reportedErrors = {};  // 防重复上报（同一错误5分钟内只上报一次）
    
    // 获取浏览器信息
    function getBrowserInfo() {
        var ua = navigator.userAgent;
        var browser = 'Unknown';
        if (ua.indexOf('Chrome') > -1) browser = 'Chrome';
        else if (ua.indexOf('Firefox') > -1) browser = 'Firefox';
        else if (ua.indexOf('Safari') > -1) browser = 'Safari';
        else if (ua.indexOf('Edge') > -1) browser = 'Edge';
        return browser + ' / ' + (navigator.platform || 'Unknown');
    }
    
    // 获取当前用户操作上下文
    function getActionContext() {
        var active = document.activeElement;
        var context = '';
        if (active) {
            context = active.tagName.toLowerCase();
            if (active.id) context += '#' + active.id;
            if (active.className) context += '.' + String(active.className).split(' ')[0];
            var text = (active.textContent || '').trim().substring(0, 50);
            if (text) context += ' "' + text + '"';
        }
        return context;
    }
    
    // 发送错误报告
    function reportError(type, message, stack) {
        // 生成错误指纹（防重复）
        var fingerprint = type + '|' + message.substring(0, 100);
        var now = Date.now();
        if (reportedErrors[fingerprint] && (now - reportedErrors[fingerprint]) < 300000) {
            return;  // 5分钟内已上报过，跳过
        }
        reportedErrors[fingerprint] = now;
        
        var payload = {
            type: type,
            message: message || 'Unknown error',
            stack: stack || '',
            url: window.location.href,
            action: getActionContext(),
            browser: getBrowserInfo(),
            timestamp: new Date().toISOString()
        };
        
        // 用 sendBeacon 确保页面卸载时也能发送
        if (navigator.sendBeacon) {
            navigator.sendBeacon(REPORT_URL, JSON.stringify(payload));
        } else {
            // 降级到 fetch
            fetch(REPORT_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                keepalive: true
            }).catch(function() {});  // 静默失败
        }
    }
    
    // 1. 捕获 JS 运行时错误
    window.addEventListener('error', function(event) {
        var msg = event.message || 'Unknown error';
        var stack = '';
        if (event.error && event.error.stack) {
            stack = event.error.stack;
        }
        reportError('js_error', msg + ' at ' + (event.filename || '') + ':' + (event.lineno || ''), stack);
    });
    
    // 2. 捕获未处理的 Promise rejection
    window.addEventListener('unhandledrejection', function(event) {
        var msg = 'Unhandled Promise rejection';
        var stack = '';
        if (event.reason) {
            if (typeof event.reason === 'string') {
                msg += ': ' + event.reason;
            } else if (event.reason.message) {
                msg += ': ' + event.reason.message;
            }
            if (event.reason.stack) {
                stack = event.reason.stack;
            }
        }
        reportError('promise_error', msg, stack);
    });
    
    // 3. 捕获按钮/链接点击后无响应或跳转失败
    var clickTimeout = null;
    document.addEventListener('click', function(event) {
        var target = event.target;
        // 只关注可交互元素
        var interactive = target.closest('button, a, [onclick], [role="button"], input[type="submit"]');
        if (!interactive) return;
        
        // × 关闭按钮（toast/notification/announcement），点击即移除，无需检测响应
        var clickedText = (target === interactive) ? interactive.innerHTML : target.textContent;
        if (clickedText.trim() === '×' || clickedText.trim() === '&times;' || (interactive.childElementCount <= 1 && interactive.innerHTML.trim().indexOf('×') > -1 && interactive.innerHTML.trim().length < 10)) return;
        
        // 菜单折叠/展开（menu-group-header），不期望导航
        if (interactive.classList.contains('menu-group-header') || interactive.closest('menu-group-header')) return;
        
        // 质量门禁模板选择卡片（g-tpl），点击只切换高亮
        if (interactive.classList.contains('g-tpl') || interactive.closest('g-tpl')) return;
        
        // 对比按钮（compare-btn-sm），点击展开内联diff
        if (interactive.classList.contains('compare-btn-sm')) return;
        
        // toggle开关（质量门禁规则开关）
        if (interactive.classList.contains('toggle')) return;
        
        // 清除上次的检测
        if (clickTimeout) clearTimeout(clickTimeout);
        
        clickTimeout = setTimeout(function() {
            // 3秒后检查：如果页面没有变化（没有导航、没有弹窗、没有loading），可能有问题
            var urlBefore = window.location.href;
            var hasLoading = document.querySelector('.loading, .spinner, [data-loading], .scan-progress');
            var hasModal = document.querySelector('.modal.show, .modal[style*="display: flex"], .modal[style*="display:block"]');
            
            var hasDiffVisible = document.querySelector('.diff-inline[style*="table-row"]');
            var hasToast = document.querySelector('#error-toast, #fix-notification');
            if (!hasLoading && !hasModal && !hasDiffVisible && !hasToast) {
                // 没有loading状态也没有弹窗，但点击后3秒什么都没发生
                // 不自动弹窗打扰用户，只静默上报
                reportError(
                    'click_no_response',
                    '点击元素无响应: ' + interactive.tagName + (interactive.id ? '#' + interactive.id : '') + ' "' + (interactive.textContent || '').trim().substring(0, 30) + '"',
                    ''
                );
            }
        }, 3000);
    });
    
    // 4. 捕获 fetch 请求失败（增强现有的 fetch wrapper）
    var _origFetchForError = window._origFetch || window.fetch;
    window._errorMonitoringFetch = true;
    
    // 监听所有 fetch 的 4xx/5xx 响应
    var origFetch = window.fetch;
    window.fetch = function(url, options) {
        return origFetch.apply(this, arguments).then(function(response) {
            if (response.status >= 500) {
                reportError(
                    'api_error',
                    'API请求失败 [' + response.status + ']: ' + (typeof url === 'string' ? url : url.toString()),
                    'Status: ' + response.status + ' ' + response.statusText
                );
            }
            return response;
        }).catch(function(error) {
            // 网络错误
            if (url !== REPORT_URL) {  // 不上报错误监控自己的请求
                reportError(
                    'network_error',
                    '网络请求失败: ' + (typeof url === 'string' ? url : url.toString()) + ' - ' + (error.message || 'Unknown'),
                    ''
                );
            }
            throw error;
        });
    };
    
    // 5. 友好提示弹窗（仅在检测到严重错误时显示）
    window.showUserFriendlyError = function(message) {
        // 移除已存在的提示
        var existing = document.getElementById('error-toast');
        if (existing) existing.remove();
        
        var toast = document.createElement('div');
        toast.id = 'error-toast';
        toast.innerHTML = '<div style="position:fixed;bottom:24px;right:24px;background:#1e293b;color:#fff;padding:16px 20px;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.2);z-index:999999;max-width:360px;font-size:14px;line-height:1.6;animation:slideInUp .3s ease;">' +
            '<div style="display:flex;align-items:flex-start;gap:12px;">' +
            '<span style="font-size:20px;">⚠️</span>' +
            '<div>' +
            '<div style="font-weight:600;margin-bottom:4px;">页面出现了一点小问题</div>' +
            '<div style="opacity:.85;font-size:13px;">' + (message || '我们已收到错误报告，技术团队正在处理中。请稍后再试。') + '</div>' +
            '<div style="margin-top:8px;opacity:.6;font-size:12px;">错误已自动上报，无需额外操作</div>' +
            '</div>' +
            '<button onclick="this.closest(\'#error-toast\').remove()" style="background:none;border:none;color:#fff;font-size:18px;cursor:pointer;opacity:.6;padding:0;line-height:1;">×</button>' +
            '</div></div>';
        document.body.appendChild(toast);
        
        // 8秒后自动消失
        setTimeout(function() {
            if (toast.parentNode) {
                toast.style.opacity = '0';
                toast.style.transition = 'opacity 0.5s';
                setTimeout(function() { toast.remove(); }, 500);
            }
        }, 8000);
    };
    
    // 添加动画样式
    if (!document.getElementById('error-toast-style')) {
        var style = document.createElement('style');
        style.id = 'error-toast-style';
        style.textContent = '@keyframes slideInUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}';
        document.head.appendChild(style);
    }
    
    console.log('[煋鉴] 错误监控系统已启用');
})();


// ============================================================
// 维护状态轮询 - 修复后自动通知在线用户
// ============================================================
(function() {
    'use strict';
    
    var CHECK_INTERVAL = 30000;  // 30秒检查一次
    var lastKnownStatus = 'normal';
    
    function checkMaintenanceStatus() {
        fetch('/api/maintenance-status')
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.status === 'fixed' && lastKnownStatus !== 'fixed') {
                    // 从非fixed变为fixed → 弹框通知用户
                    showFixNotification(data.message || '问题已修复，请重试操作。');
                    lastKnownStatus = 'fixed';
                } else if (data.status === 'fixing' && lastKnownStatus === 'normal') {
                    // 正在维护中
                    lastKnownStatus = 'fixing';
                    // 不主动打扰用户，只在用户下次操作失败时提示
                } else if (data.status === 'normal') {
                    lastKnownStatus = 'normal';
                }
            })
            .catch(function() {});  // 静默失败
    }
    
    function showFixNotification(message) {
        // 移除已有通知
        var existing = document.getElementById('fix-notification');
        if (existing) existing.remove();
        
        var notification = document.createElement('div');
        notification.id = 'fix-notification';
        notification.innerHTML = 
            '<div style="position:fixed;top:0;left:0;right:0;z-index:999998;background:linear-gradient(135deg,#10b981,#059669);color:#fff;padding:16px 24px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.15);animation:slideDown .4s ease;">' +
            '<div style="display:flex;align-items:center;justify-content:center;gap:12px;max-width:600px;margin:0 auto;">' +
            '<span style="font-size:24px;">✅</span>' +
            '<div style="text-align:left;">' +
            '<div style="font-weight:700;font-size:15px;">问题已修复</div>' +
            '<div style="font-size:13px;opacity:.9;margin-top:2px;">' + message + '</div>' +
            '</div>' +
            '<button onclick="this.closest(\'#fix-notification\').remove()" style="background:rgba(255,255,255,.2);border:none;color:#fff;width:28px;height:28px;border-radius:50%;cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">×</button>' +
            '</div></div>';
        
        document.body.appendChild(notification);
        
        // 15秒后自动消失
        setTimeout(function() {
            if (notification.parentNode) {
                notification.firstElementChild.style.transition = 'transform .4s ease, opacity .4s ease';
                notification.firstElementChild.style.transform = 'translateY(-100%)';
                notification.firstElementChild.style.opacity = '0';
                setTimeout(function() { notification.remove(); }, 400);
            }
        }, 15000);
    }
    
    // 添加动画
    if (!document.getElementById('fix-notification-style')) {
        var style = document.createElement('style');
        style.id = 'fix-notification-style';
        style.textContent = '@keyframes slideDown{from{transform:translateY(-100%)}to{transform:translateY(0)}}';
        document.head.appendChild(style);
    }
    
    // 启动轮询（延迟5秒后开始，避免首屏加载时请求）
    setTimeout(function() {
        checkMaintenanceStatus();  // 首次检查
        setInterval(checkMaintenanceStatus, CHECK_INTERVAL);
    }, 5000);
    
    console.log('[煋鉴] 维护状态监控已启用（每30秒检查）');
})();
