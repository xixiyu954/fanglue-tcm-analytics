const telemetry = require('../../utils/telemetry');
const quiz = require('../../utils/quiz');

Page({
  data: {
    expGroup: 'B_jaccard',
    modeLabel: '智能相似辨析',
    todayCount: 0,
    progressPct: 0,
    streakDays: 1,
    masteredCount: 0,
    stepIndex: 0,
    focusCategory: '',
    question: null,
    answered: false,
    selectedLabel: '',
    lastCorrect: false,
    diffExplanation: '',
  },

  recentNames: [],
  qStartAt: 0,

  onLoad(options) {
    const user = telemetry.getUser();
    const expGroup = user.exp_group || 'B_jaccard';
    this.setData({
      expGroup,
      modeLabel: expGroup === 'B_jaccard' ? '相似方智能辨析' : '教材章节精练',
      streakDays: user.streak_days || 1,
      focusCategory: (options && options.category) || '',
    });
    this.refreshStats();
    this.loadNextQuestion();
    telemetry.trackEvent('quiz', 'page_view', { exp_group: expGroup });
  },

  onShow() {
    const focus = wx.getStorageSync('fl_focus_category');
    if (focus) {
      wx.removeStorageSync('fl_focus_category');
      this.setData({ focusCategory: focus });
      this.loadNextQuestion();
    }
    this.refreshStats();
  },

  refreshStats() {
    const logs = telemetry.getQuizLogs();
    const today = telemetry.todayStr();
    const todayCount = logs.filter((x) => (x.ts || '').slice(0, 10) === today).length;
    const sm2 = telemetry.getSM2State();
    this.setData({
      todayCount,
      progressPct: Math.min(100, Math.round((todayCount / 10) * 100)),
      masteredCount: Object.keys(sm2).length,
    });
  },

  clearFocus() {
    this.setData({ focusCategory: '' });
    this.loadNextQuestion();
  },

  loadNextQuestion() {
    const q = quiz.generateQuestion(
      this.data.expGroup,
      this.data.stepIndex,
      this.recentNames,
      this.data.focusCategory
    );
    this.recentNames.push(q.formula);
    if (this.recentNames.length > 12) this.recentNames.shift();
    this.qStartAt = Date.now();
    this.setData({
      question: q,
      answered: false,
      selectedLabel: '',
      lastCorrect: false,
      diffExplanation: '',
    });
  },

  onChooseOption(e) {
    if (this.data.answered) return;
    const label = e.currentTarget.dataset.label;
    const q = this.data.question;
    const chosenObj = q.options.find((o) => o.label === label);
    const isCorrect = Boolean(chosenObj && chosenObj.isCorrect);
    const durationMs = Date.now() - this.qStartAt;

    let diffExplanation = '';
    if (!isCorrect && q.q_type === 'similar_discriminate' && chosenObj) {
      const more = (chosenObj.more || []).join('、');
      const less = (chosenObj.less || []).join('、');
      diffExplanation = `你误选的「${label}」与正答相比：` +
        (more ? `多了【${more}】` : '无多出药') + '，' +
        (less ? `少了【${less}】` : '无缺少药') + `（组成相似度 ${chosenObj.sim}）。`;
    } else if (isCorrect && q.q_type === 'similar_discriminate') {
      diffExplanation = `本组干扰项最高相似度 ${q.distractor_max_sim}，你准确区分出了核心配伍差异。`;
    }

    if (q.q_type !== 'incompat_rule') {
      quiz.updateSM2(q.formula, isCorrect);
    }
    telemetry.trackQuiz({
      formula: q.formula,
      category: q.category,
      q_type: q.q_type,
      chosen: label,
      distractor_max_sim: q.distractor_max_sim,
      is_correct: isCorrect,
      duration_ms: durationMs,
      is_review: q.is_review,
    });

    this.setData({
      answered: true,
      selectedLabel: label,
      lastCorrect: isCorrect,
      diffExplanation,
    });
    this.refreshStats();
  },

  onNextQuestion() {
    this.setData({ stepIndex: this.data.stepIndex + 1 });
    this.loadNextQuestion();
  },

  onShareAppMessage() {
    const user = telemetry.getUser();
    const q = this.data.question;
    telemetry.trackEvent('quiz', 'share_click', { formula: q ? q.formula : '' });
    return {
      title: q ? `考考你：这组药对应哪首经典名方？（${q.category}）` : '方略随身 · 中药方剂每日辨析',
      path: `/pages/quiz/quiz?inviter=${user.user_hash}&card_type=quiz_challenge`,
    };
  },
});
