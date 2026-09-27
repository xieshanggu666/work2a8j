window.TicketsView = {
  data() { return { tickets: [], error: "" }; },
  created() { this.load(); },
  methods: {
    async load() { try { this.tickets = await Api.get("/api/tickets"); } catch (e) { this.error = e.message; } },
    async resolve(t) {
      try { await Api.post(`/api/tickets/${t.id}/resolve`); await this.load(); }
      catch (e) { this.error = e.message; }
    },
    lvZh(l) { return { minor: "轻微", major: "较大", critical: "重大" }[l] || l; },
    stZh(s) { return { open: "未处理", processing: "处理中", resolved: "待复查", closed: "已关闭" }[s] || s; },
  },
  computed: {
    sorted() { return [...this.tickets].sort((a, b) => { const w={critical:0,major:1,minor:2}; return (w[a.level]||9)-(w[b.level]||9); }); },
  },
  template: `
  <div>
    <h1 class="page-title">缺陷隐患工单</h1>
    <div v-if="error" class="msg err">{{ error }}</div>
    <div v-if="!sorted.length" class="dim pad">暂无工单，执行巡检任务后自动生成缺陷工单。</div>
    <div v-for="t in sorted" :key="t.id" class="ticket" :class="t.level">
      <div class="tk-left">
        <span class="chip lv" :class="t.level">{{ lvZh(t.level) }}</span>
        <strong>{{ t.title }}</strong>
        <span class="dim">{{ t.code }}</span>
      </div>
      <div class="tk-mid">
        <div class="dim">{{ t.detail }}</div>
      </div>
      <div class="tk-right">
        <span class="chip" :class="t.status">{{ stZh(t.status) }}</span>
        <button class="btn tiny" v-if="t.status==='open'" @click="resolve(t)">处理</button>
        <button class="btn tiny ghost" v-else-if="t.status==='resolved'" @click="resolve(t)">关闭</button>
      </div>
    </div>
  </div>`,
};