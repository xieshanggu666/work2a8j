window.LinesView = {
  emits: ["nav"],
  data() { return { lines: [], sel: null, error: "" }; },
  created() { this.load(); },
  methods: {
    async load() { try { this.lines = await Api.get("/api/lines"); } catch (e) { this.error = e.message; } },
    async select(l) { this.sel = await Api.get(`/api/lines/${l.id}`); },
    riskZh(r) { return { normal: "正常", suspect: "可疑", key: "重点" }[r] || r; },
    lineRiskZh(r) { return zhRisk[r] || r; },
    newMission(l) { this.$emit("nav", "missions"); },
  },
  template: `
  <div>
    <h1 class="page-title">线路台账</h1>
    <div v-if="error" class="msg err">{{ error }}</div>
    <div class="split">
      <div class="list-panel">
        <div v-for="l in lines" :key="l.id" class="row-item" :class="{on: sel && sel.id===l.id}" @click="select(l)">
          <div class="item-main">
            <strong>{{ l.code }}</strong> {{ l.name }}
            <span class="chip">杆塔 {{ l.tower_count }}</span>
            <span class="chip risk" :class="l.risk_level">{{ lineRiskZh(l.risk_level) }}</span>
            <span v-if="l.open_ticket_count" class="chip open">未闭环 {{ l.open_ticket_count }}</span>
          </div>
          <div class="item-sub">{{ l.voltage_kv }}kV · {{ l.total_km }}km · {{ {in_service:'运行',maintenance:'检修'}[l.status] }}</div>
        </div>
      </div>
      <div class="detail-panel" v-if="sel">
        <h3>{{ sel.code }} {{ sel.name }}</h3>
        <p class="dim">{{ sel.voltage_kv }}kV · 全长 {{ sel.total_km }}km · 共 {{ sel.towers.length }} 基杆塔</p>
        <div class="tower-list">
          <div v-for="t in sel.towers" :key="t.id" class="tower" :class="t.risk_hint">
            <span class="tw-title">{{ t.code }}</span>
            <span class="dim">#{{ t.seq }} · {{ t.cum_km }}km</span>
            <span class="chip" :class="t.risk_hint">{{ riskZh(t.risk_hint) }}</span>
            <span class="dim coord">{{ t.lat }}, {{ t.lng }}</span>
          </div>
        </div>
        <button class="btn primary" @click="newMission(sel)">为本线路规划巡检任务</button>
      </div>
    </div>
  </div>`,
};