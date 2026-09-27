window.FleetView = {
  data() { return { drones: [], batts: [], error: "" }; },
  created() { this.load(); },
  methods: {
    async load() {
      try {
        const [d, b] = await Promise.all([Api.get("/api/drones"), Api.get("/api/batteries")]);
        this.drones = d; this.batts = b;
      } catch (e) { this.error = e.message; }
    },
    socPct(v) { return Math.round(v * 100); },
    barColor(v) { return v < 0.25 ? "#e5484d" : v < 0.55 ? "#ffb300" : "#43c87a"; },
  },
  template: `
  <div>
    <h1 class="page-title">机队与电池</h1>
    <div v-if="error" class="msg err">{{ error }}</div>
    <h3>无人机机队</h3>
    <div class="grid">
      <div v-for="d in drones" :key="d.id" class="panel">
        <div class="panel-h"><strong>{{ d.code }}</strong><span class="chip" :class="d.status">{{ d.status }}</span></div>
        <div class="dim">{{ d.model }}</div>
        <div class="soc-row"><span>电量</span>
          <span class="track"><span class="fill" :style="{width: socPct(d.battery_soc)+'%', background: barColor(d.battery_soc)}"></span></span>
          <b>{{ socPct(d.battery_soc) }}%</b>
        </div>
        <div class="dim">载荷 {{ d.max_payload }}kg</div>
      </div>
    </div>
    <h3>电池包</h3>
    <div class="grid">
      <div v-for="b in batts" :key="b.id" class="panel">
        <div class="panel-h"><strong>{{ b.code }}</strong><span class="chip" :class="b.status">{{ b.status }}</span></div>
        <div class="row-line"><span>续航</span><b>{{ b.capacity_km }}km</b></div>
        <div class="soc-row"><span>电量</span>
          <span class="track"><span class="fill" :style="{width: socPct(b.soc)+'%', background: barColor(b.soc)}"></span></span>
          <b>{{ socPct(b.soc) }}%</b>
        </div>
        <div class="dim">循环 {{ b.cycle_count }} 次</div>
      </div>
    </div>
  </div>`,
};