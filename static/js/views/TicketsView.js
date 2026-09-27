window.TicketsView = {
  data() {
    return {
      tickets: [], error: "",
      tab: "all",
      openId: null, detail: null,
      form: { assignee: "", due_hours: null, note: "", reviewer: "", reason: "" },
    };
  },
  created() { this.load(); },
  computed: {
    counts() {
      const c = { all: this.tickets.length, open: 0, processing: 0, resolved: 0, overdue: 0, closed: 0 };
      for (const t of this.tickets) {
        c[t.status] = (c[t.status] || 0) + 1;
        if (t.overdue) c.overdue += 1;
      }
      return c;
    },
    filtered() {
      const w = { critical: 0, major: 1, minor: 2 };
      const list = this.tab === "all" ? this.tickets
        : this.tab === "overdue" ? this.tickets.filter(t => t.overdue)
        : this.tickets.filter(t => t.status === this.tab);
      return [...list].sort((a, b) => (w[a.level] ?? 9) - (w[b.level] ?? 9));
    },
  },
  methods: {
    async load() {
      try { this.tickets = await Api.get("/api/tickets"); }
      catch (e) { this.error = e.message; }
    },
    async toggle(t) {
      if (this.openId === t.id) { this.openId = null; this.detail = null; return; }
      this.openId = t.id;
      this.form = { assignee: t.assignee || "", due_hours: null, note: "", reviewer: "", reason: "" };
      try { this.detail = await Api.get(`/api/tickets/${t.id}`); }
      catch (e) { this.error = e.message; }
    },
    async act(url, body) {
      this.error = "";
      try {
        await Api.post(url, body);
        await this.load();
        if (this.openId) this.detail = await Api.get(`/api/tickets/${this.openId}`);
      } catch (e) { this.error = e.message; }
    },
    doAssign(t) {
      if (!this.form.assignee.trim()) { this.error = "请填写处理人"; return; }
      this.act(`/api/tickets/${t.id}/assign`, {
        assignee: this.form.assignee.trim(),
        due_hours: this.form.due_hours || null,
      });
    },
    doSubmit(t) { this.act(`/api/tickets/${t.id}/submit`, { note: this.form.note }); },
    doReview(t, approve) {
      if (!this.form.reviewer.trim()) { this.error = "请填写复核人"; return; }
      if (!approve && !this.form.reason.trim()) { this.error = "退回必须填写退回原因"; return; }
      this.act(`/api/tickets/${t.id}/review`, {
        reviewer: this.form.reviewer.trim(), approve, reason: this.form.reason.trim(),
      });
    },
    lvZh(l) { return zhLevel[l] || l; },
    stZh(s) { return zhTicketStatus[s] || s; },
    actZh(a) { return zhTicketAction[a] || a; },
    fmt,
  },
  template: `
  <div>
    <h1 class="page-title">缺陷隐患工单</h1>
    <div class="tabs">
      <a :class="{active: tab==='all'}" @click="tab='all'">全部 {{ counts.all }}</a>
      <a :class="{active: tab==='open'}" @click="tab='open'">待处理 {{ counts.open }}</a>
      <a :class="{active: tab==='processing'}" @click="tab='processing'">处理中 {{ counts.processing }}</a>
      <a :class="{active: tab==='resolved'}" @click="tab='resolved'">待复核 {{ counts.resolved }}</a>
      <a :class="{active: tab==='overdue'}" @click="tab='overdue'">已超时 <b class="danger-text">{{ counts.overdue }}</b></a>
      <a :class="{active: tab==='closed'}" @click="tab='closed'">已关闭 {{ counts.closed }}</a>
    </div>
    <div v-if="error" class="msg err">{{ error }}</div>
    <div v-if="!filtered.length" class="dim pad">暂无工单，执行巡检任务后自动生成缺陷工单。</div>

    <div v-for="t in filtered" :key="t.id" class="ticket" :class="[t.level, {over: t.overdue}]">
      <div class="tk-head" @click="toggle(t)">
        <div class="tk-left">
          <span class="chip lv" :class="t.level">{{ lvZh(t.level) }}</span>
          <strong>{{ t.title }}</strong>
          <span class="dim">{{ t.code }} · {{ t.mission_code }}</span>
        </div>
        <div class="tk-right">
          <span v-if="t.overdue" class="chip overdue">已超时</span>
          <span v-if="t.reject_count" class="chip">退回 {{ t.reject_count }} 次</span>
          <span class="chip" :class="t.status">{{ stZh(t.status) }}</span>
          <span class="dim">{{ openId===t.id ? '▲' : '▼' }}</span>
        </div>
      </div>
      <div class="dim tk-sub">
        {{ t.detail }}
        <span v-if="t.assignee"> · 处理人 {{ t.assignee }}</span>
        <span v-if="t.due_at && t.status!=='closed'"> · 时限 {{ fmt(t.due_at) }}</span>
      </div>

      <div v-if="openId===t.id && detail" class="tk-body">
        <div class="kv-grid">
          <div class="kv-row"><span>处理人</span><b>{{ t.assignee || '未派单' }}</b></div>
          <div class="kv-row"><span>派单时间</span><b>{{ fmt(t.assigned_at) }}</b></div>
          <div class="kv-row"><span>处理时限</span><b :class="{'danger-text': t.overdue}">{{ fmt(t.due_at) }}<template v-if="t.overdue">（已超时）</template></b></div>
          <div class="kv-row"><span>处理说明</span><b>{{ t.resolve_note || '—' }}</b></div>
          <div class="kv-row"><span>复核人</span><b>{{ t.reviewer || '—' }}</b></div>
          <div class="kv-row"><span>关闭时间</span><b>{{ fmt(t.closed_at) }}</b></div>
          <div class="kv-row" v-if="t.reject_reason"><span>最近退回原因</span><b class="danger-text">{{ t.reject_reason }}</b></div>
        </div>

        <!-- 状态操作区 -->
        <div class="tk-form" v-if="t.status==='open' || t.status==='processing'">
          <template v-if="t.status==='open'">
            <input v-model="form.assignee" placeholder="处理人姓名" />
            <select v-model.number="form.due_hours">
              <option :value="null">默认时限（重大24h/较大72h/轻微168h）</option>
              <option :value="24">24 小时</option>
              <option :value="48">48 小时</option>
              <option :value="72">72 小时</option>
              <option :value="168">7 天</option>
            </select>
            <button class="btn tiny primary" @click="doAssign(t)">派单</button>
          </template>
          <template v-else>
            <input v-model="form.note" placeholder="处理说明（处置措施、消缺结果）" />
            <button class="btn tiny primary" @click="doSubmit(t)">提交处理</button>
            <input v-model="form.assignee" placeholder="改派处理人" class="w-sm" />
            <button class="btn tiny ghost" @click="doAssign(t)">改派</button>
          </template>
        </div>
        <div class="tk-form" v-else-if="t.status==='resolved'">
          <input v-model="form.reviewer" placeholder="复核人姓名" />
          <input v-model="form.reason" placeholder="退回原因（退回时必填）" />
          <button class="btn tiny primary" @click="doReview(t, true)">复核通过</button>
          <button class="btn tiny danger" @click="doReview(t, false)">退回</button>
        </div>
        <div class="dim" v-else>工单已闭环。</div>

        <!-- 流转记录 -->
        <div class="timeline" v-if="detail.events && detail.events.length">
          <div v-for="e in detail.events" :key="e.id" class="tl-item">
            <span class="tl-dot" :class="e.action"></span>
            <span class="tl-act">{{ actZh(e.action) }}</span>
            <span class="dim">{{ e.actor }} · {{ fmt(e.created_at) }}</span>
            <span class="tl-note">{{ e.note }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>`,
};
