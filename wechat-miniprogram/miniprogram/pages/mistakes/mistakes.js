const quiz = require('../../utils/quiz');
const telemetry = require('../../utils/telemetry');

Page({
  data: {
    summary: { totalLogs: 0, totalRight: 0, overallAcc: 0, catStats: [], topConfused: [], topWrong: [] },
  },

  onShow() {
    this.setData({ summary: quiz.computeMistakeSummary() });
    telemetry.trackEvent('mistakes', 'page_view');
  },

  goQuiz() {
    wx.switchTab({ url: '/pages/quiz/quiz' });
  },

  practiceCategory(e) {
    const cat = e.currentTarget.dataset.cat;
    if (!cat || cat === '配伍安全') return;
    wx.setStorageSync('fl_focus_category', cat);
    wx.switchTab({ url: '/pages/quiz/quiz' });
  },

  inspectFormula(e) {
    const name = e.currentTarget.dataset.name;
    wx.setStorageSync('fl_inspect_formula', name);
    wx.switchTab({ url: '/pages/check/check' });
  },
});
