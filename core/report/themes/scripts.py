"""
煋鉴(Xinpect) 主题系统 - 通用JS交互脚本
包含搜索、视图切换、分组展开/折叠等交互逻辑
"""


def get_javascript() -> str:
    """获取完整的JS脚本"""
    return '''
(function() {
    'use strict';

    var currentView = 'severity';
    var allCards = [];
    var TOTAL = 0;

    var LEVEL_META = {
        'blocking':   { label: '🚫 阻断 (Blocking)', dot: 'dot-blocking',   order: 0 },
        'error':      { label: '🚫 阻断 (Blocking)', dot: 'dot-blocking',   order: 0 },
        'problem':    { label: '🟡 警告 (Problem)',  dot: 'dot-problem',    order: 1 },
        'warning':    { label: '🟡 警告 (Problem)',  dot: 'dot-problem',    order: 1 },
        'suggestion': { label: '💡 建议 (Suggestion)', dot: 'dot-suggestion', order: 2 },
        'info':       { label: '💡 建议 (Suggestion)', dot: 'dot-suggestion', order: 2 }
    };

    function init() {
        var raw = document.getElementById('rawIssuesData');
        if (!raw) return;
        var cards = raw.querySelectorAll('.issue-card');
        TOTAL = cards.length;
        for (var i = 0; i < cards.length; i++) {
            var c = cards[i];
            allCards.push({
                html: c.outerHTML,
                level: c.getAttribute('data-level') || 'info',
                file: c.getAttribute('data-file') || '',
                brain: c.getAttribute('data-brain') || '',
                search: (c.getAttribute('data-search') || '').toLowerCase()
            });
        }

        document.getElementById('searchInput').addEventListener('input', debounce(apply, 200));
        render();
    }

    function getFiltered() {
        var q = (document.getElementById('searchInput').value || '').toLowerCase().trim();
        if (!q) return allCards.slice();
        return allCards.filter(function(c) {
            return c.search.indexOf(q) !== -1;
        });
    }

    function apply() {
        var filtered = getFiltered();
        var sc = document.getElementById('searchCount');
        var q = document.getElementById('searchInput').value.trim();
        if (q) {
            sc.textContent = filtered.length + ' / ' + TOTAL;
            sc.classList.add('visible');
        } else {
            sc.classList.remove('visible');
        }
        document.getElementById('resultCount').innerHTML =
            '显示 <strong>' + filtered.length + '</strong> / ' + TOTAL + ' 项';
        render();
    }

    function render() {
        var filtered = getFiltered();
        var container = document.getElementById('issuesContainer');

        if (filtered.length === 0) {
            container.innerHTML = '<div class="no-results">🔍 未找到匹配的问题</div>';
            return;
        }

        var groups;
        if (currentView === 'severity') {
            groups = groupBySeverity(filtered);
        } else if (currentView === 'file') {
            groups = groupByFile(filtered);
        } else {
            groups = groupByBrain(filtered);
        }

        var h = '';
        for (var i = 0; i < groups.length; i++) {
            h += buildGroup(groups[i].title, groups[i].count, groups[i].cards, groups[i].dot);
        }
        container.innerHTML = h;
    }

    function groupBySeverity(cards) {
        var map = {}, order = [];
        for (var i = 0; i < cards.length; i++) {
            var lv = cards[i].level;
            if (!map[lv]) { map[lv] = []; order.push(lv); }
            map[lv].push(cards[i]);
        }
        order.sort(function(a, b) {
            return (LEVEL_META[a] ? LEVEL_META[a].order : 9) - (LEVEL_META[b] ? LEVEL_META[b].order : 9);
        });
        return order.map(function(lv) {
            var m = LEVEL_META[lv] || { label: lv, dot: '' };
            return { title: m.label, count: map[lv].length, cards: map[lv], dot: m.dot };
        });
    }

    function groupByFile(cards) {
        var map = {}, order = [];
        for (var i = 0; i < cards.length; i++) {
            var f = cards[i].file || '(全局)';
            if (!map[f]) { map[f] = []; order.push(f); }
            map[f].push(cards[i]);
        }
        order.sort();
        return order.map(function(f) {
            return { title: '📄 ' + f, count: map[f].length, cards: map[f], dot: '' };
        });
    }

    function groupByBrain(cards) {
        var map = {}, order = [];
        for (var i = 0; i < cards.length; i++) {
            var b = cards[i].brain || 'Brain 8 (业务安全)';
            if (!map[b]) { map[b] = []; order.push(b); }
            map[b].push(cards[i]);
        }
        return order.map(function(b) {
            return { title: '🧠 ' + b, count: map[b].length, cards: map[b], dot: '' };
        });
    }

    function buildGroup(title, count, cards, dot) {
        var dotHtml = dot ? '<span class="group-level-dot ' + dot + '"></span>' : '';
        var cardsHtml = '';
        for (var i = 0; i < cards.length; i++) {
            cardsHtml += cards[i].html;
        }
        return '<div class="group-section">' +
            '<div class="group-header" onclick="toggleGroup(this)">' +
                '<span class="group-arrow">▼</span>' +
                dotHtml +
                '<span class="group-title">' + escHtml(title) + '</span>' +
                '<span class="group-count">' + count + '项</span>' +
            '</div>' +
            '<div class="group-content">' + cardsHtml + '</div>' +
        '</div>';
    }

    function escHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // 全局 API
    window.switchView = function(view) {
        currentView = view;
        var tabs = document.querySelectorAll('.view-tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabs[i].getAttribute('data-view') === view);
        }
        render();
    };

    window.toggleGroup = function(header) {
        header.parentElement.classList.toggle('collapsed');
    };

    window.expandAll = function() {
        var gs = document.querySelectorAll('.group-section');
        for (var i = 0; i < gs.length; i++) {
            gs[i].classList.remove('collapsed');
        }
        var cs = document.querySelectorAll('.issue-card');
        for (var i = 0; i < cs.length; i++) {
            if (cs[i].querySelector('.issue-detail') && cs[i].querySelector('.issue-detail').innerHTML.trim()) {
                cs[i].classList.add('expanded');
            }
        }
    };

    window.collapseAll = function() {
        var gs = document.querySelectorAll('.group-section');
        for (var i = 0; i < gs.length; i++) {
            gs[i].classList.add('collapsed');
        }
        var cs = document.querySelectorAll('.issue-card');
        for (var i = 0; i < cs.length; i++) {
            cs[i].classList.remove('expanded');
        }
    };

    function debounce(fn, ms) {
        var t;
        return function() {
            clearTimeout(t);
            t = setTimeout(fn, ms);
        };
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

// ============ 建议区独立逻辑 ============
(function() {
    'use strict';
    var sugView = 'severity';
    var sugCards = [];
    var SUG_TOTAL = 0;

    var SUG_LEVEL_META = {
        'suggestion': { label: '💡 优化建议', dot: 'dot-suggestion', order: 0 },
        'info':       { label: 'ℹ️ 信息提示', dot: 'dot-suggestion', order: 1 }
    };

    function initSug() {
        var raw = document.getElementById('rawSuggestionsData');
        if (!raw) return;
        var cards = raw.querySelectorAll('.issue-card');
        SUG_TOTAL = cards.length;
        for (var i = 0; i < cards.length; i++) {
            var c = cards[i];
            sugCards.push({
                html: c.outerHTML,
                level: c.getAttribute('data-level') || 'suggestion',
                file: c.getAttribute('data-file') || '',
                brain: c.getAttribute('data-brain') || '',
                search: (c.getAttribute('data-search') || '').toLowerCase()
            });
        }
        var inp = document.getElementById('sugSearchInput');
        if (inp) inp.addEventListener('input', debounce(applySug, 200));
        renderSug();
    }

    function getFilteredSug() {
        var q = ((document.getElementById('sugSearchInput') || {}).value || '').toLowerCase().trim();
        if (!q) return sugCards.slice();
        return sugCards.filter(function(c) { return c.search.indexOf(q) !== -1; });
    }

    function applySug() {
        var filtered = getFilteredSug();
        var sc = document.getElementById('sugSearchCount');
        var q = (document.getElementById('sugSearchInput').value || '').trim();
        if (q) {
            sc.textContent = filtered.length + ' / ' + SUG_TOTAL;
            sc.classList.add('visible');
        } else {
            sc.classList.remove('visible');
        }
        document.getElementById('sugResultCount').innerHTML =
            '显示 <strong>' + filtered.length + '</strong> / ' + SUG_TOTAL + ' 项';
        renderSug();
    }

    function renderSug() {
        var filtered = getFilteredSug();
        var container = document.getElementById('suggestionsContainer');
        if (!container) return;
        if (filtered.length === 0) {
            container.innerHTML = '<div class="no-results">🔍 未找到匹配的建议</div>';
            return;
        }
        var groups;
        if (sugView === 'severity') {
            groups = groupSugByLevel(filtered);
        } else if (sugView === 'file') {
            groups = groupSugByFile(filtered);
        } else {
            groups = groupSugByBrain(filtered);
        }
        var h = '';
        for (var i = 0; i < groups.length; i++) {
            h += buildGroup(groups[i].title, groups[i].count, groups[i].cards, groups[i].dot);
        }
        container.innerHTML = h;
    }

    function groupSugByLevel(cards) {
        var map = {}, order = [];
        for (var i = 0; i < cards.length; i++) {
            var lv = cards[i].level;
            if (!map[lv]) { map[lv] = []; order.push(lv); }
            map[lv].push(cards[i]);
        }
        order.sort(function(a, b) {
            return (SUG_LEVEL_META[a] ? SUG_LEVEL_META[a].order : 9) - (SUG_LEVEL_META[b] ? SUG_LEVEL_META[b].order : 9);
        });
        return order.map(function(lv) {
            var m = SUG_LEVEL_META[lv] || { label: lv, dot: '' };
            return { title: m.label, count: map[lv].length, cards: map[lv], dot: m.dot };
        });
    }

    function groupSugByFile(cards) {
        var map = {}, order = [];
        for (var i = 0; i < cards.length; i++) {
            var f = cards[i].file || '(全局)';
            if (!map[f]) { map[f] = []; order.push(f); }
            map[f].push(cards[i]);
        }
        order.sort();
        return order.map(function(f) {
            return { title: '📄 ' + f, count: map[f].length, cards: map[f], dot: '' };
        });
    }

    function groupSugByBrain(cards) {
        var map = {}, order = [];
        for (var i = 0; i < cards.length; i++) {
            var b = cards[i].brain || 'Brain 8 (业务安全)';
            if (!map[b]) { map[b] = []; order.push(b); }
            map[b].push(cards[i]);
        }
        return order.map(function(b) {
            return { title: '🧠 ' + b, count: map[b].length, cards: map[b], dot: '' };
        });
    }

    function buildGroup(title, count, cards, dot) {
        var dotHtml = dot ? '<span class="group-level-dot ' + dot + '"></span>' : '';
        var cardsHtml = '';
        for (var i = 0; i < cards.length; i++) {
            cardsHtml += cards[i].html;
        }
        return '<div class="group-section">' +
            '<div class="group-header" onclick="toggleSugGroup(this)">' +
                '<span class="group-arrow">▼</span>' +
                dotHtml +
                '<span class="group-title">' + escHtml(title) + '</span>' +
                '<span class="group-count">' + count + '项</span>' +
            '</div>' +
            '<div class="group-content">' + cardsHtml + '</div>' +
        '</div>';
    }

    function escHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function debounce(fn, ms) {
        var t;
        return function() { clearTimeout(t); t = setTimeout(fn, ms); };
    }

    window.switchSugView = function(view) {
        sugView = view;
        var tabs = document.querySelectorAll('#sugViewTabs .view-tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabs[i].getAttribute('data-view') === view);
        }
        renderSug();
    };

    window.toggleSugGroup = function(header) {
        header.parentElement.classList.toggle('collapsed');
    };

    window.expandAllSug = function() {
        var gs = document.querySelectorAll('#suggestions-section .group-section');
        for (var i = 0; i < gs.length; i++) gs[i].classList.remove('collapsed');
        var cs = document.querySelectorAll('#suggestions-section .issue-card');
        for (var i = 0; i < cs.length; i++) {
            if (cs[i].querySelector('.issue-detail') && cs[i].querySelector('.issue-detail').innerHTML.trim())
                cs[i].classList.add('expanded');
        }
    };

    window.collapseAllSug = function() {
        var gs = document.querySelectorAll('#suggestions-section .group-section');
        for (var i = 0; i < gs.length; i++) gs[i].classList.add('collapsed');
        var cs = document.querySelectorAll('#suggestions-section .issue-card');
        for (var i = 0; i < cs.length; i++) cs[i].classList.remove('expanded');
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSug);
    } else {
        initSug();
    }
})();
'''
