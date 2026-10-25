
// スマホではXアプリを直接開く（アプリ内ブラウザで毎回ログインを求められないように）。
// アプリが開かなかったときだけ、1.5秒後にブラウザ版Xを開く。
function shareX(text){
  const web = 'https://x.com/intent/post?text=' + encodeURIComponent(text);
  if (!/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) { window.open(web, '_blank', 'noopener'); return; }
  const fallback = setTimeout(() => { if (!document.hidden) location.href = web; }, 1500);
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearTimeout(fallback); }, { once: true });
  location.href = 'twitter://post?message=' + encodeURIComponent(text);
}

// 日付は日本時間で数える（スマホの時計の設定によらず同じ結果にする）
const PC = (() => {
  const WD = '日月火水木金土';
  const jst = () => new Date(Date.now() + 9 * 3600e3);
  const today = () => jst().toISOString().slice(0, 10);
  const utc = s => { const p = s.slice(0, 10).split('-').map(Number); return Date.UTC(p[0], p[1] - 1, p[2]); };
  const days = s => Math.round((utc(s) - utc(today())) / 864e5);
  const dateJa = s => { const p = s.slice(0, 10).split('-').map(Number); return `${p[0]}年${p[1]}月${p[2]}日（${WD[new Date(utc(s)).getUTCDay()]}）`; };
  // 締切の表示。残り1〜3日（と当日）は赤、4〜7日はオレンジ。色だけに頼らないよう、文字でも伝える
  function due(dl, time){
    const n = days(dl);
    const closed = n < 0 || (n === 0 && !!time && jst().toISOString().slice(11, 16) > time);
    if (n < 0) return { n, cls: 'red', label: '募集は終了しました', closed };
    if (closed) return { n, cls: 'red', label: `本日${time}で受付終了`, closed };
    if (n === 0) return { n, cls: 'red', label: time ? `⚠ 今日が締切（${time}まで）` : '⚠ 今日が締切', closed };
    if (n <= 3) return { n, cls: 'red', label: `⚠ 締切間近：あと${n}日`, closed };
    if (n <= 7) return { n, cls: 'orange', label: `⏰ もうすぐ締切：あと${n}日`, closed };
    return { n, cls: '', label: `締切まで あと${n}日`, closed };
  }
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ss = {
    get(k){ try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set(k, v){ try { sessionStorage.setItem(k, v); } catch (e) {} },
  };
  // 上部ボタンの件数（締切日ごとの数から、今日以降のものだけ数え直す）
  function navCounts(C){
    const t = today();
    document.querySelectorAll('[data-count]').forEach(el => {
      const c = (C || {})[el.dataset.count];
      if (!c) return;
      el.textContent = Object.keys(c).reduce((s, d) => s + (d >= t ? c[d] : 0), 0);
      el.parentNode.hidden = false;
    });
  }
  // いちばん新しい件数（毎朝の更新の最後に作られる counts.json）で、上部ボタンの件数を数え直す
  const root = document.documentElement.dataset.root;
  if (root != null && window.fetch && location.protocol !== 'file:') {
    fetch(root + 'counts.json', { cache: 'no-cache' }).then(r => r.ok ? r.json() : null)
      .then(j => { if (j) navCounts(j.counts); }).catch(() => {});
  }
  // Xで共有の小窓
  const dlg = document.getElementById('share-dialog');
  const box = document.getElementById('share-text');
  const msg = document.getElementById('share-msg');
  function openShare(text){
    box.value = text; box.scrollTop = 0; msg.textContent = '';
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
    document.getElementById('share-post').focus();
  }
  function closeShare(){ if (dlg.close) dlg.close(); else dlg.removeAttribute('open'); }
  // 文章のコピー。新しいしくみが使えないブラウザでは、昔ながらの方法でコピーする
  function copyText(text){
    const legacy = () => {
      const ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.top = '0'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, text.length);
      let ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
      ta.remove(); return ok;
    };
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(() => true, legacy);
    return Promise.resolve(legacy());
  }
  if (dlg) {
    document.getElementById('share-post').onclick = () => shareX(box.value);
    document.getElementById('share-copy').onclick = () => copyText(box.value).then(ok => {
      msg.textContent = ok ? 'コピーしました。Xアプリなどに貼り付けてください。' : 'コピーできませんでした。上の文章を長押し（または選択）してコピーしてください。';
      if (!ok) { box.focus(); box.select(); }
    });
    document.getElementById('share-close').onclick = closeShare;
    dlg.addEventListener('click', e => { if (e.target === dlg) closeShare(); });
  }
  // ページの上へ戻るボタン
  const top = document.getElementById('totop');
  if (top) {
    const f = () => { top.hidden = window.scrollY < 600; };
    window.addEventListener('scroll', f, { passive: true }); f();
    top.onclick = () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      const h = document.querySelector('h1'); if (h) { h.setAttribute('tabindex', '-1'); h.focus({ preventScroll: true }); }
    };
  }
  return { today, days, dateJa, due, esc, ss, navCounts, openShare, copyText };
})();
