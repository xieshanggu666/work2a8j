// 无人机电力巡检 —— 前端 API 封装
const Api = {
  async request(method, url, body) {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const j = await res.json().catch(() => ({}));
      throw new Error(j.detail || "请求失败");
    }
    return res.json();
  },
  get(url) { return this.request("GET", url); },
  post(url, body) { return this.request("POST", url, body); },
  del(url) { return this.request("DELETE", url); },
};

const pct = (v) => (v == null ? "-" : Math.round(v * 100) + "%");
const fmt = (v) => (v ? String(v).replace("T", " ").slice(5, 16) : "—");
const zhStatus = {
  planned: "待执行", in_progress: "执行中", completed: "已完成", canceled: "已取消",
};
const zhPriority = { high: "高", normal: "中", low: "低" };
const zhLevel = { minor: "轻微", major: "较大", critical: "重大" };
const zhLineStatus = { in_service: "运行", maintenance: "检修" };
const zhTicketStatus = { open: "待处理", processing: "处理中", resolved: "待复核", closed: "已关闭" };
const zhTicketAction = { create: "创建", assign: "派单", submit: "提交处理", approve: "复核通过", reject: "复核退回" };
const zhRisk = { normal: "正常", suspect: "关注", key: "重点" };