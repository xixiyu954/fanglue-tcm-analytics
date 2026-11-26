const analysis = require('../../utils/analysis');
const telemetry = require('../../utils/telemetry');

const HOT_NAMES = ['四君子汤', '桂枝汤', '麻黄汤', '小柴胡汤', '逍遥散', '白虎汤', '清营汤', '六味地黄丸', '血府逐瘀汤', '二陈汤', '补中益气汤', '归脾汤'];

Page({
  data: {
    mode: 'classic',
    keyword: '',
    candidates: [],
    selectedName: '四君子汤',
    freeText: '人参9 白术9 茯苓9 炙甘草6 陈皮6 半夏9',
    unmatchedText: '',
    title: '',
    metaText: '',
    report: null,
  },

  onLoad(options) {
    this.setData({ candidates: this.getCandidates('') });
    const initFormula = (options && options.formula && analysis.getFormulaByName(options.formula))
      ? options.formula
      : '四君子汤';
    this.loadClassic(initFormula);
    telemetry.trackEvent('check', 'page_view');
  },

  onShow() {
    const inspect = wx.getStorageSync('fl_inspect_formula');
    if (inspect && analysis.getFormulaByName(inspect)) {
      wx.removeStorageSync('fl_inspect_formula');
      this.setData({ mode: 'classic' });
      this.loadClassic(inspect);
    }
  },

  getCandidates(kw) {
    const s = String(kw || '').trim();
    if (!s) {
      return HOT_NAMES.map((n) => analysis.getFormulaByName(n)).filter(Boolean);
    }
    return analysis.FORMULAS.filter(
      (f) => f.n.indexOf(s) !== -1 || f.cat.indexOf(s) !== -1 || f.src.indexOf(s) !== -1
    ).slice(0, 16);
  },

  switchMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({ mode });
    if (mode === 'free') this.runFreeCheck();
  },

  onSearchInput(e) {
    const kw = e.detail.value;
    this.setData({ keyword: kw, candidates: this.getCandidates(kw) });
  },

  selectClassic(e) {
    const name = e.currentTarget.dataset.name;
    this.setData({ mode: 'classic' });
    this.loadClassic(name);
  },

  loadClassic(name) {
    const f = analysis.getFormulaByName(name);
    if (!f) return;
    const items = f.h.map((x) => ({ herb: x[0], dose_g: x[1], herb_raw: x[2] || x[0], processing: '' }));
    const report = analysis.analyzeComposition(items, f.n);
    this.setData({
      selectedName: f.n,
      title: f.n,
      metaText: `${f.dyn}《${f.src}》· ${f.cat}`,
      report,
    });
    telemetry.trackEvent('check', 'formula_checked', { mode: 'classic', formula: f.n, alerts: report.alerts.length });
  },

  onFreeInput(e) {
    this.setData({ freeText: e.detail.value });
  },

  fillDangerDemo() {
    this.setData({ freeText: '甘草6 海藻9 附子6 半夏9 关木通6' });
    this.runFreeCheck();
  },

  runFreeCheck() {
    const { items, unmatched } = analysis.parseFormulaText(this.data.freeText);
    if (!items.length) {
      wx.showToast({ title: '请输入至少一味标准药材', icon: 'none' });
      return;
    }
    const report = analysis.analyzeComposition(items, '');
    this.setData({
      title: '自拟方体检',
      metaText: report.total_dose ? `总剂量 ${report.total_dose}g` : '等量计权',
      unmatchedText: unmatched.join('、'),
      report,
    });
    telemetry.trackEvent('check', 'formula_checked', { mode: 'free', n_herbs: items.length, alerts: report.alerts.length });
  },

  onShareAppMessage() {
    const user = telemetry.getUser();
    const fname = this.data.mode === 'classic' ? this.data.selectedName : '四君子汤';
    telemetry.trackEvent('check', 'share_click', { formula: fname });
    return {
      title: `「${fname}」性味归经与配伍安全体检报告`,
      path: `/pages/check/check?formula=${encodeURIComponent(fname)}&inviter=${user.user_hash}&card_type=formula_card`,
    };
  },
});
