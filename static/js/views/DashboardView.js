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
  },
  template: `
  <div>
    <h1 class="page-title">运行总览</h1>
    <div v-if="error" class="msg err">{{ error }}</div>
    <div class="cards" v-if="ov">
      <div class="card" @click="$emit('nav','lines')"><div class="k">线路</div><div class="v">{{ ov.lines }}</div><div class="hint">输电线路条数</div></div>
      <div class="card" @click="$emit('nav','lines')"><div class="k">杆塔</div><div class="v">{{ ov.towers }}</div><div class="hint">巡检对象</div></div>
      <div class="card" @click="$emit('nav','fleet')"><div class="k">无人机</div><div class="v">{{ ov.drones }}</div><div class="hint">机队规模</div></div>
      <div class="card" @click="$emit('nav','missions')"><div class="k">任务</div><div class="v">{{ ov.missions }}</div><div class="hint">巡检任务总数</div></div>
      <div class="card" @click="$emit('nav','missions')"><div class="k">已完成</div><div class="v ok">{{ ov.completed }}</div><div class="hint">闭环任务</div></div>
      <div class="card" @click="$emit('nav','tickets')"><div class="k">待处理缺陷</div><div class="v warn">{{ ov.open_tickets }}</div><div class="hint">未关闭工单</div></div>
      <div class="card" @click="$emit('nav','tickets')"><div class="k">重大缺陷</div><div class="v danger">{{ ov.critical }}</div><div class="hint">critical 级</div></div>
      <div class="card"><div class="k">飞行记录</div><div class="v">{{ ov.flights }}</div><div class="hint">合规放行航次</div></div>
    </div>
  </div>`,
};