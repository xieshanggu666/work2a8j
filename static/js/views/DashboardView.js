window.DashboardView = {
  props: [],
  emits: ["nav"],
  data() { return { ov: null, error: "" }; },
  created() { this.load(); },
  methods: {
    async load() {
      try { this.ov = await Api.get("/api/overview"); }
      catch (e) { this.error = e.message; }
    },
    riskZh(r) { return zhRisk[r] || r; },
  },
  template: `
  <div>
    <h1 class="page-title">运行总览</h1>
    <div v-if="error" class="msg err">{{ error }}</div>
    <div class="cards" v-if="ov">
      <div class="card" @click="$emit('nav','lines')"><div class="k">线路</div><div class="v">{{ ov.lines }}</div><div class="hint">输电线路条数</div></div>
      <div class="card" @click="$emit('nav','fleet')"><div class="k">无人机</div><div class="v">{{ ov.drones }}</div><div class="hint">机队规模</div></div>
      <div class="card" @click="$emit('nav','missions')"><div class="k">任务</div><div class="v">{{ ov.missions }}</div><div class="hint">已完成 {{ ov.completed }}</div></div>
      <div class="card"><div class="k">飞行记录</div><div class="v">{{ ov.flights }}</div><div class="hint">合规放行航次</div></div>
      <div class="card" @click="$emit('nav','tickets')"><div class="k">待处理缺陷</div><div class="v warn">{{ ov.open_tickets }}</div><div class="hint">待派单工单</div></div>
      <div class="card" @click="$emit('nav','tickets')"><div class="k">处理中</div><div class="v">{{ ov.processing }}</div><div class="hint">已派单待处理</div></div>
      <div class="card" @click="$emit('nav','tickets')"><div class="k">待复核</div><div class="v">{{ ov.resolved }}</div><div class="hint">等待复核闭环</div></div>
      <div class="card" @click="$emit('nav','tickets')"><div class="k">超时工单</div><div class="v danger">{{ ov.overdue }}</div><div class="hint">超过处理时限</div></div>
    </div>

    <div class="panel risk-panel" v-if="ov && ov.line_risks && ov.line_risks.length">
      <div class="panel-h">
        <h3 class="risk-title">线路风险统计</h3>
        <span class="dim">由未闭环缺陷工单实时回写</span>
      </div>
      <div v-for="r in ov.line_risks" :key="r.id" class="risk-row" @click="$emit('nav','lines')">
        <span class="chip risk" :class="r.risk_level">{{ riskZh(r.risk_level) }}</span>
        <strong>{{ r.code }}</strong>
        <span>{{ r.name }}</span>
        <span class="risk-stat">未闭环工单 <b :class="{'danger-text': r.open_ticket_count>0}">{{ r.open_ticket_count }}</b></span>
        <span class="risk-stat">超时 <b :class="{'danger-text': r.overdue>0}">{{ r.overdue }}</b></span>
      </div>
    </div>
  </div>`,
};
