// 方略随身 · 小程序入口：初始化匿名用户、A/B 分流、渠道归因与微信云开发
const telemetry = require('./utils/telemetry');

// ⚠️ 开通微信云开发后，将你的云环境 ID 填到此处即可实时上报云数据库；
// 留空时自动以「本地离线模式」流畅运行，支持全部功能与一键导出 JSON 日志供后台分析！
const CLOUD_ENV_ID = '';

App({
  globalData: {
    cloudEnabled: false,
    user: null,
    sessionId: '',
    webPlatformUrl: 'https://fanglue-tcm.streamlit.app',
  },

  onLaunch(options) {
    if (CLOUD_ENV_ID && wx.cloud) {
      try {
        wx.cloud.init({ env: CLOUD_ENV_ID, traceUser: false });
        this.globalData.cloudEnabled = true;
      } catch (e) {
        this.globalData.cloudEnabled = false;
      }
    }

    const scene = String((options && options.scene) || '1001');
    const query = (options && options.query) || {};
    const inviter = query.inviter || '';
    const user = telemetry.initUser({ scene, inviter });
    this.globalData.user = user;
    this.globalData.sessionId = telemetry.newSessionId();

    telemetry.trackEvent('app', 'app_launch', {
      scene,
      inviter,
      exp_group: user.exp_group,
      entry_formula: query.formula || '',
    });

    if (inviter && inviter !== user.user_hash && user.is_new) {
      telemetry.trackShareConversion({
        inviter_hash: inviter,
        invitee_hash: user.user_hash,
        card_type: query.card_type || 'formula_card',
      });
    }
  },
});
