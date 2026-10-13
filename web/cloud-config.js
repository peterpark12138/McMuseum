// 麦麦复活赛 · WorkBuddy Cloud Service 公开配置
// 仅含前端安全的 publicConfig（endpoint / oauthRelayBaseUrl / publishableKey），
// 不含任何密钥；这些值可安全出现在前端代码中（publishableKey 仅标识应用、无权限）。
window.CLOUD_CONFIG = {
  endpoint: "https://mcmuseum-revival.app.workbuddy.host",
  oauthRelayBaseUrl: "https://www.workbuddy.cn/v2/as/genie-baas/oauth",
  publishableKey: "wbpk_BvqPGWuQ6kAFqhVAXh1FE4_V4sx8n4ipg9s6n8S0ahAwLeq4EoB7glh"
};
