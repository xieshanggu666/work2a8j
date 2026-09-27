window.TicketsView = {
  data() {
    return {
      tickets: [], error: "",
      panel: 0, action: "",            // 行内操作面板：当前工单 + 动作
      assignee: "", resolution: "", reviewer: "", reason: "",
    };
  },
  created() { this.load(); },
  methods: {
    async load() { try { this.tickets = await Api.get("/api/tickets"); } catch (e) { this.error = e.message; } },
    openAct(t, action) {
      this.panel = t.id; this.action = action; this.error = "";
      this.assignee = t.assignee || ""; this.resolution = ""; this.reviewer = ""; this.reason = "";
    },
    cancelAct() { this.panel = 0; this.action = ""; },
    async confirm(t) {
      this.error = "";
      const id = t.id;
      try {
        if (this.action === "assign") {
          if (!this.assignee.trim()) { this.error = "请填写处理人"; return; }
          await Api.post(`/api/tickets/${id}/assign`, { assignee: this.assignee.trim() });
        } else if (this.action === "submit") {
          await Api.post(`/api/tickets/${id}/submit`, { resolution: this.resolution.trim() });
        } else if (this.action === "approve") {
          await Api.post(`/api/tickets/${id}/review`, { approve: true, reviewer: this.reviewer.trim() });
        } else if (this.action === "reject") {
          if (!this.reason.trim()) { this.error = "退回必须填写退回原因"; return; }
          await Api.post(`/api/tickets/${id}/review`, { approve: false, reviewer: this.reviewer.trim(), reason: this.reason.trim() });
        }
        this.cancelAct();
        await this.load();
      } catch (e) { this.error = e.message; }
    },
    lvZh(l) { return { minor: "轻微", major: "较大", critical: "重大" }[l] || l; },
    stZh(s) { return { open: "待处理", processing: "处理中", resolved: "待复核", returned: "已退回", closed: "已关闭" }[s] || s; },
    fmtTime(v) { return v ? String(v).replace("T", " ").slice(0, 16) : "—"; },
    remain(t) {
      if (!t.due_at || t.status === "closed") return "";
      const h = Math.round((new Date(t.due_at) - Date.now()) / 36e5);
      return h >= 0 ? `剩 ${h}h` : `已超时 ${-h}h`;
    },
  },
  computed: {
    sorted() { return [...this.tickets].sort((a, b) => { const w={critical:0,major:1,minor:2}; return (w[a.level]??9)-(w[b.level]??9); }); },
    stats() {
      const s = { open: 0, processing: 0, resolved: 0, returned: 0, overdue: 0 };
      for (const t of this.tickets) {
        if (s[t.status] != null) s[t.status]++;
        if (t.overdue) s.overdue++;
      }
      return s;
    },
  },
  template: `
  <div>
    <h1 class="page-title">缺陷隐患工单</h1>
    <div v-if="error" class="msg err">{{ error }}</div>

    <!-- 闭环状态统计条 -->
    <div class="tk-stats" v-if="tickets.length">
      <span class="chip open">待处理 {{ stats.open }}</span>
      <span class="chip processing">处理中 {{ stats.processing }}</span>
      <span class="chip resolved">待复核 {{ stats.resolved }}</span>
      <span class="chip returned">已退回 {{ stats.returned }}</span>
      <span class="chip overdue">超时 {{ stats.overdue }}</span>
    </div>

    <div v-if="!sorted.length" class="dim pad">暂无工单，执行巡检任务后自动生成缺陷工单。</div>
    <div v-for="t in sorted" :key="t.id" class="ticket" :class="[t.level, {overdue: t.overdue}]">
      <div class="tk-left">
        <span class="chip lv" :class="t.level">{{ lvZh(t.level) }}</span>
        <strong>{{ t.title }}</strong>
        <span class="dim">{{ t.code }}</span>
        <span v-if="t.overdue" class="chip overdue">超时</span>
      </div>
      <div class="tk-mid">
        <div class="dim">{{ t.detail }}</div>
        <div class="tk-meta">
          <span>处理人：{{ t.assignee || '未派单' }}</span>
          <span>时限 {{ t.sla_hours }}h<template v-if="t.status!=='closed'">（{{ remain(t) }}）</template></span>
          <span v-if="t.reviewer">复核人：{{ t.reviewer }}</span>
          <span v-if="t.return_count">退回 {{ t.return_count }} 次：{{ t.return_reason }}</span>
        </div>
        <div class="tk-meta" v-if="t.resolution">处理结果：{{ t.resolution }}</div>
      </div>
      <div class="tk-right">
        <span class="chip" :class="t.status">{{ stZh(t.status) }}</span>
        <button class="btn tiny" v-if="t.status==='open'" @click="openAct(t,'assign')">派单处理</button>
        <button class="btn tiny" v-else-if="t.status==='returned'" @click="openAct(t,'assign')">重新派单</button>
        <button class="btn tiny" v-else-if="t.status==='processing'" @click="openAct(t,'submit')">提交复核</button>
        <template v-else-if="t.status==='resolved'">
          <button class="btn tiny primary" @click="openAct(t,'approve')">复核通过</button>
          <button class="btn tiny ghost" @click="openAct(t,'reject')">退回</button>
        </template>
      </div>

      <!-- 行内操作面板 -->
      <div v-if="panel===t.id" class="tk-act">
        <template v-if="action==='assign'">
          <label>处理人<input v-model="assignee" placeholder="如：检修一班 张三" /></label>
        </template>
        <template v-else-if="action==='submit'">
          <label>处理结果说明<input v-model="resolution" placeholder="如：已更换绝缘子，复测合格" /></label>
        </template>
        <template v-else>
          <label>复核人<input v-model="reviewer" placeholder="如：运检主管 李四" /></label>
          <label v-if="action==='reject'">退回原因<input v-model="reason" placeholder="如：消缺不彻底，需复检" /></label>
        </template>
        <div class="form-actions">
          <button class="btn tiny primary" @click="confirm(t)">确认</button>
          <button class="btn tiny ghost" @click="cancelAct">取消</button>
        </div>
      </div>
    </div>
  </div>`,
};
