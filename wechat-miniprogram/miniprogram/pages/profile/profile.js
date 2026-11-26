const { HERBS } = require('../../utils/analysis');
const telemetry = require('../../utils/telemetry');

function formatHerb(h) {
  return Object.assign({}, h, {
    flavorsStr: (h.f || []).join('、') || '—',
    meridiansStr: (h.m || []).join('、') || '—',
    doseStr: h.d ? `${h.d[0]}~${h.d[1]}g` : '按药典/教材',
  });
}

Page({
  data: {
    user: {},
    cloudEnabled: false,
    quizCount: 0,
    eventCount: 0,
    herbKw: '',
    herbResults: [],
  },

  onShow() {
    const app = getApp();
    this.setData({
      user: telemetry.getUser(),
      cloudEnabled: Boolean(app && app.globalData && app.globalData.cloudEnabled),
      quizCount: telemetry.getQuizLogs().length,
      eventCount: telemetry.getEvents().length,
      herbResults: this.searchHerbs(this.data.herbKw),
    });
    telemetry.trackEvent('profile', 'page_view');
  },

  searchHerbs(kw) {
    const s = String(kw || '').trim();
    const list = s
      ? HERBS.filter(
          (h) => h.n.indexOf(s) !== -1 || h.c.indexOf(s) !== -1 || (h.m || []).join('').indexOf(s) !== -1
        )
      : HERBS.slice(0, 8);
    return list.slice(0, 12).map(formatHerb);
  },

  onHerbSearch(e) {
    const kw = e.detail.value;
    this.setData({ herbKw: kw, herbResults: this.searchHerbs(kw) });
  },

  copyWebUrl() {
    wx.setClipboardData({
      data: 'https://fanglue-tcm.streamlit.app',
      success: () => wx.showToast({ title: '已复制 Web 平台地址', icon: 'success' }),
    });
  },

  exportLogs() {
    const json = telemetry.exportBundleJson();
    wx.setClipboardData({
      data: json,
      success: () => wx.showToast({ title: '已复制 JSON，可导入后台看板', icon: 'none' }),
    });
  },
});
