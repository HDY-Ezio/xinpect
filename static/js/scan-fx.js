/* 煋鉴扫描等待界面 · 全站唯一一份（2026-11-05）
 *
 * 铁律：进度只认后端真实事件。
 *   · 本文件没有定时器循环、没有自己推进百分比、没有随机数参与进度
 *   · pct / text / events / files 全部来自 render(data) 的参数，即扫描器真实快照
 *   · 拿不到数据就只显示「检测中」，绝不自己编阶段、绝不假装还剩几秒
 *   · 动画与音效只是装饰，不表达进度、不阻塞请求、不抢鼠标
 */
(function (global) {
  'use strict';

  var KEY_SOUND = 'xp_scan_sfx';
  var KEY_MOTION = 'xp_scan_motion';
  var S = {
    root: null, pct: -1, eventCount: 0, sound: true, reduced: false,
    finished: false, n: {}
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function $(id) { return document.getElementById(id); }
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) { } }
  function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

  /* 现场合成音效：不下载音频文件、不自动播放、音量压得很低、可一键关闭 */
  var AudioFX = (function () {
    var ctx = null;
    function ensure() {
      if (!ctx) {
        var AC = global.AudioContext || global.webkitAudioContext;
        if (!AC) return null;
        try { ctx = new AC(); } catch (e) { return null; }
      }
      if (ctx.state === 'suspended') { try { ctx.resume(); } catch (e) { } }
      return ctx;
    }
    function tone(freq, dur, vol, delay, type) {
      var c = ensure();
      if (!c) return;
      try {
        var o = c.createOscillator(), g = c.createGain();
        o.type = type || 'sine';
        o.frequency.value = freq;
        var t = c.currentTime + (delay || 0);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.linearRampToValueAtTime(vol, t + 0.012);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        o.connect(g); g.connect(c.destination);
        o.start(t); o.stop(t + dur + 0.02);
      } catch (e) { }
    }
    return {
      start: function () { tone(330, 0.09, 0.026, 0); tone(440, 0.10, 0.022, 0.08); },
      tick: function () { tone(520, 0.05, 0.012, 0); },
      done: function () {
        tone(392, 0.11, 0.020, 0); tone(494, 0.11, 0.020, 0.09);
        tone(587, 0.18, 0.024, 0.18);
      },
      test: function () {
        this.start();
        var self = this;
        setTimeout(function () { self.tick(); }, 260);
        setTimeout(function () { self.done(); }, 540);
      }
    };
  })();

  var MARKUP =
    '<div class="xp-sfx-head">' +
    '<div class="xp-sfx-title">正在检测你的代码</div>' +
    '<div class="xp-sfx-toggles">' +
    '<button type="button" class="xp-sfx-btn" data-xp="sound" aria-pressed="true">音效：开</button>' +
    '<button type="button" class="xp-sfx-btn" data-xp="test">试听三声</button>' +
    '</div></div>' +
    '<div class="xp-sfx-screen" aria-hidden="true">' +
    '<div class="xp-sfx-codeflow"><i></i><i></i><i></i><i></i><i></i></div>' +
    '<div class="xp-sfx-beam"></div>' +
    '<div class="xp-sfx-particles"><span></span><span></span><span></span><span></span><span></span><span></span></div>' +
    '<div class="xp-sfx-screen-label">XINSPECT / LIVE SCAN</div>' +
    '<div class="xp-sfx-caret"></div>' +
    '</div>' +
    '<div class="xp-sfx-current" data-xp="current">检测中…</div>' +
    '<div class="xp-sfx-meta" data-xp="meta">等待扫描引擎返回实际进度</div>' +
    '<div class="xp-sfx-bar"><div class="xp-sfx-fill" data-xp="fill"></div></div>' +
    '<div class="xp-sfx-pct" data-xp="pct">检测中</div>' +
    '<div class="xp-sfx-log">' +
    '<div class="xp-sfx-log-title">实际检查记录</div>' +
    '<div data-xp="log"></div></div>' +
    '<div class="xp-sfx-files" data-xp="files"></div>' +
    '<div class="xp-sfx-note">这里只显示扫描引擎真实完成的步骤，没有估算，也没有预计剩余时间。</div>';

  function pick() {
    var q = S.root.querySelectorAll('[data-xp]');
    for (var i = 0; i < q.length; i++) {
      var k = q[i].getAttribute('data-xp');
      if (k !== 'sound' && k !== 'test') S.n[k] = q[i];
    }
    S.n.sound = S.root.querySelector('[data-xp="sound"]');
    S.n.test = S.root.querySelector('[data-xp="test"]');
  }

  function syncSound() {
    if (!S.n.sound) return;
    S.n.sound.textContent = '音效：' + (S.sound ? '开' : '关');
    S.n.sound.setAttribute('aria-pressed', S.sound ? 'true' : 'false');
  }

  function mount(el, opts) {
    var target = typeof el === 'string' ? $(el) : el;
    if (!target) return null;
    opts = opts || {};
    S.root = target;
    S.pct = -1; S.eventCount = 0; S.finished = false;
    S.reduced = (global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches) ||
      read(KEY_MOTION) === '0';
    var saved = read(KEY_SOUND);
    S.sound = saved === null ? !S.reduced : saved !== '0';
    S.root.className = 'xp-scanfx' + (S.reduced ? ' is-reduced' : '');
    S.root.innerHTML = MARKUP;
    S.root.style.display = 'block';
    pick();
    syncSound();

    if (S.n.sound) {
      S.n.sound.addEventListener('click', function () {
        S.sound = !S.sound;
        store(KEY_SOUND, S.sound ? '1' : '0');
        syncSound();
        if (S.sound) AudioFX.tick();
      });
    }
    if (S.n.test) {
      S.n.test.addEventListener('click', function () { AudioFX.test(); });
    }
    if (opts.title && S.n.title) S.n.title.textContent = opts.title;
    if (S.sound) AudioFX.start();
    return api;
  }

  /* 只按后端真实数据渲染。data = {pct, text, events, files, engines_done, engines_total} */
  function render(data) {
    if (!S.root || !data) return;
    var d = data;
    if (typeof d.pct === 'number' && isFinite(d.pct)) {
      var v = Math.max(0, Math.min(100, d.pct));
      if (v >= S.pct) {
        S.pct = v;
        if (S.n.fill) S.n.fill.style.transform = 'scaleX(' + (v / 100) + ')';
        if (S.n.pct) S.n.pct.textContent = v >= 100 ? '检测完成' : v + '% · 按实际完成的检查项';
      }
    } else if (S.n.pct) {
      S.n.pct.textContent = '检测中（等待引擎返回实际进度）';
    }

    if (S.n.current) {
      S.n.current.textContent = d.text ? d.text : '检测中…';
    }

    var done = typeof d.engines_done === 'number' ? d.engines_done : null;
    var total = typeof d.engines_total === 'number' ? d.engines_total : null;
    if (S.n.meta) {
      var bits = [];
      if (done !== null && total !== null && total > 0) bits.push('已完成 ' + done + '/' + total + ' 项检查');
      if (Array.isArray(d.files) && d.files.length) bits.push('共 ' + d.files.length + ' 个文件');
      S.n.meta.textContent = bits.length ? bits.join(' · ') : '等待扫描引擎返回实际进度';
    }

    var evs = Array.isArray(d.events) ? d.events : [];
    if (S.n.log) {
      var html = '';
      var start = Math.max(0, evs.length - 7);
      for (var i = evs.length - 1; i >= start; i--) {
        var e = evs[i] || {};
        var kind = String(e.kind || 'stage');
        var label = { file: '文件', engine: '引擎', stage: '阶段', done: '完成' }[kind] || '阶段';
        var ms = typeof e.t === 'number' ? (e.t / 1000).toFixed(1) + 's' : '';
        html += '<div class="xp-sfx-line" data-kind="' + esc(kind) + '">' +
          '<span class="xp-sfx-kind">' + label + '</span>' +
          '<span>' + esc(e.label) + '</span>' +
          '<span class="xp-sfx-time">' + esc(ms) + '</span></div>';
      }
      if (!html) html = '<div class="xp-sfx-line" data-kind="stage"><span class="xp-sfx-kind">等待</span><span>正在连接扫描引擎</span><span class="xp-sfx-time"></span></div>';
      S.n.log.innerHTML = html;
    }

    if (evs.length > S.eventCount) {
      if (S.sound && !S.finished && S.eventCount > 0) AudioFX.tick();
      S.eventCount = evs.length;
    }

    var files = Array.isArray(d.files) ? d.files : [];
    if (S.n.files) {
      var fh = '';
      var max = Math.min(files.length, 10);
      for (var j = 0; j < max; j++) {
        var active = (files.length > 1 && j === (S.eventCount % files.length)) ? ' is-active' : '';
        fh += '<span class="xp-sfx-file' + active + '">' + esc(files[j]) + '</span>';
      }
      if (files.length > max) fh += '<span class="xp-sfx-file">等 ' + files.length + ' 个文件</span>';
      S.n.files.innerHTML = fh;
    }
  }

  function finish(ok) {
    if (!S.root) return;
    S.finished = true;
    S.root.className += ' is-finished';
    if (ok && S.sound) AudioFX.done();
  }

  function hide() {
    if (!S.root) return;
    S.root.style.display = 'none';
    S.root.innerHTML = '';
    S.root = null; S.n = {};
  }

  var api = { mount: mount, render: render, finish: finish, hide: hide };
  global.XpScanFX = api;
})(window);
