/* 无人机电力巡检 —— 应用入口 */
const { createApp } = Vue;

const App = {
  components: { DashboardView, LinesView, FleetView, MissionsView, TicketsView },
  data() {
    return { tab: "dashboard" };
  },
  methods: {
    setTab(t) { this.tab = t; },
  },
  template: `
  <div class="app">
    <nav class="nav">
      <span class="brand">无人机电力巡检<span class="dot"></span>任务规划</span>
      <a :class="{active: tab==='dashboard'}" @click="setTab('dashboard')">总览</a>
      <a :class="{active: tab==='lines'}" @click="setTab('lines')">线路台账</a>
      <a :class="{active: tab==='fleet'}" @click="setTab('fleet')">机队电池</a>
      <a :class="{active: tab==='missions'}" @click="setTab('missions')">巡检任务</a>
      <a :class="{active: tab==='tickets'}" @click="setTab('tickets')">缺陷工单</a>
    </nav>
    <div class="container">
      <DashboardView v-if="tab==='dashboard'" @nav="setTab" />
      <LinesView v-else-if="tab==='lines'" @nav="setTab" />
      <FleetView v-else-if="tab==='fleet'" />
      <MissionsView v-else-if="tab==='missions'" @nav="setTab" />
      <TicketsView v-else-if="tab==='tickets'" />
    </div>
  </div>`,
};

createApp(App).mount("#app");