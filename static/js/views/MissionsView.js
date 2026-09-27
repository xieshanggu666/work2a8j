window.MissionsView = {
  data() {
    return {
      missions: [], lines: [], towers: [],
      error: "",
      showForm: false,
      form: { name: "", line_id: null, start_tower_id: null, end_tower_id: null, priority: "normal" },
      sel: null,
    };
  },
  created() { this.load(); },
  methods: {
    async load() {
      try {
        this.missions = await Api.get("/api/missions");
        this.lines = await Api.get("/api/lines");
      } catch (e) { this.error = e.message; }
    },
    async openForm() {
      this.showForm = true;
      await this.pickLine(this.lines[0]);
    },
    async pickLine(line) {
      this.form.line_id = line.id;
      this.linesData = await Api.get(`/api/lines/${line.id}`);
      this.towers = this.linesData.towers;
      this.form.start_tower_id = this.towers[0] ? this.towers[0].id : null;
      this.form.end_tower_id = this.towers.length ? this.towers[this.towers.length - 1].id : null;
    },
    async create() {
      this.error = "";
      try {
        const m = await Api.post("/api/missions", this.form);
        this.showForm = false;
        Object.assign(this.form, { name: "", line_id: null, start_tower_id: null, end_tower_id: null, priority: "normal" });
        await this.load();
        this.sel = m;
      } catch (e) { this.error = e.message; }
    },
    async execute(mid) {
      this.error = "";
      try {
        await Api.post(`/api/missions/${mid}/execute`, { weather_ok: true });
        await this.load();
        this.sel = await Api.get(`/api/missions/${mid}`);
      } catch (e) { this.error = e.message; }
    },
    async select(m) { this.sel = await Api.get(`/api/missions/${m.id}`); },
    stZh(s) { return { planned: "待执行", in_progress: "执行中", completed: "已完成", canceled: "已取消" }[s] || s; },
    prZh(s) { return { high: "高", normal: "中", low: "低" }[s] || s; },
    trCode(t) { return this.towers.find(x => x.id === t); },
  },
  template: `
  <div>
    <div class="page-head">
      <h1 class="page-title">巡检任务规划</h1>
      <button class="btn primary" @click="openForm">新建任务</button>
    </div>
    <div v-if="error" class="msg err">{{ error }}</div>

    <!-- 新建表单 -->
    <div v-if="showForm" class="form-panel">
      <h3>规划新任务</h3>
      <div class="form-grid">
        <label>任务名称<input v-model="form.name" placeholder="如：环城一线例行巡检" /></label>
        <label>线路
          <select :value="form.line_id" @change="pickLine(lines.find(l=>l.id==Number($event.target.value)))">
            <option v-for="l in lines" :key="l.id" :value="l.id">{{ l.code }} {{ l.name }}</option>
          </select>
        </label>
        <label>起始杆塔
          <select v-model.number="form.start_tower_id"><option v-for="t in towers" :key="t.id" :value="t.id">{{ t.code }} (#{{ t.seq }})</option></select>
        </label>
        <label>终止杆塔
          <select v-model.number="form.end_tower_id"><option v-for="t in towers" :key="t.id" :value="t.id">{{ t.code }} (#{{ t.seq }})</option></select>
        </label>
        <label>优先级
          <select v-model="form.priority"><option value="high">高</option><option value="normal">中</option><option value="low">低</option></select>
        </label>
      </div>
      <div class="form-actions">
        <button class="btn primary" @click="create">自动规划并分配</button>
        <button class="btn ghost" @click="showForm=false">取消</button>
      </div>
      <p class="dim">系统将自动生成沿杆塔的航线并计算所需电量，再从机队中选择最合适（电能余量最小但足够）的无人机+电池组合。</p>
    </div>

    <div class="split">
      <!-- 列表 -->
      <div class="list-panel">
        <div v-for="m in missions" :key="m.id" class="row-item" :class="{on: sel && sel.id===m.id}" @click="select(m)">
          <div class="item-main">
            <strong>{{ m.code }}</strong>
            <span class="chip" :class="m.status">{{ stZh(m.status) }}</span>
            <span class="chip prio" :class="m.priority">{{ prZh(m.priority) }}优先</span>
          </div>
          <div class="item-sub">{{ m.name }} · {{ m.line_code }} · 航线 {{ m.plan_km }}km</div>
        </div>
        <div v-if="!missions.length" class="dim pad">暂无任务</div>
      </div>

      <!-- 详情 -->
      <div class="detail-panel" v-if="sel">
        <h3>{{ sel.name }} <span class="chip" :class="sel.status">{{ stZh(sel.status) }}</span></h3>
        <div class="kv-row"><span>任务编号</span><b>{{ sel.code }}</b></div>
        <div class="kv-row"><span>所属线路</span><b>{{ sel.line_code }}</b></div>
        <div class="kv-row"><span>规划航线</span><b>{{ sel.plan_km }} km / {{ sel.images_count }} 座塔</b></div>
        <div class="kv-row"><span>估算耗电</span><b>{{ Math.round(sel.estimated_battery_pct*100) }}%（含安全余量）</b></div>
        <div class="kv-row"><span>分配无人机</span><b>{{ sel.drone_code || '未分配(电量不足)' }}</b></div>
        <div class="kv-row"><span>分配电池</span><b>{{ sel.battery_code || '—' }}</b></div>
        <div class="kv-row"><span>缺陷工单</span><b>{{ sel.tickets_count }}</b></div>
        <div class="kv-row"><span>优先级</span><b>{{ prZh(sel.priority) }}</b></div>
        <div v-if="sel.status==='planned'" class="form-actions">
          <button class="btn primary" @click="execute(sel.id)">执行巡检</button>
        </div>
        <div class="route-panel" v-if="sel.route">
          <h4>航线（{{ sel.route.length }} 个航点）</h4>
          <div class="route-line">
            <span v-for="(w,i) in sel.route" :key="i" class="wp">
              <i>{{ i+1 }}</i>{{ w.code }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>`,
};