import { createApp, computed, onMounted, ref } from './vendor/vue.esm-browser.prod.js';
import { api, session } from './api.js';
import { MODEL_HINTS, MODEL_LABELS, daysAgoISO, money, percent, roas, todayISO } from './format.js';
import ChannelTable from './components/ChannelTable.js';
import ModelMatrix from './components/ModelMatrix.js';
import JourneyExplorer from './components/JourneyExplorer.js';

const App = {
  components: { ChannelTable, ModelMatrix, JourneyExplorer },

  setup() {
    const accounts = ref([]);
    const accountId = ref(null);
    const fromDay = ref(daysAgoISO(29));
    const toDay = ref(todayISO());
    const model = ref('linear');

    const report = ref(null);
    const compare = ref(null);
    const recent = ref([]);
    const journey = ref(null);
    const selectedUid = ref(null);

    const error = ref('');
    const loading = ref(true);
    const journeyLoading = ref(false);

    const models = Object.keys(MODEL_LABELS);
    const totals = computed(() => (report.value ? report.value.totals : null));
    const unattributed = computed(() => (totals.value ? totals.value.unattributed_conversions : 0));

    async function load() {
      if (!accountId.value) return;
      loading.value = true;
      session.accountId = accountId.value;

      try {
        const [current, matrix, journeys] = await Promise.all([
          api.report({ model: model.value, from: fromDay.value, to: toDay.value }),
          api.compare({ from: fromDay.value, to: toDay.value }),
          api.recent(),
        ]);
        report.value = current;
        compare.value = matrix;
        recent.value = journeys;
        error.value = '';

        const stillThere = journeys.some((row) => row.conversion_uid === selectedUid.value);
        if (!stillThere) {
          selectedUid.value = null;
          journey.value = null;
        }
      } catch (err) {
        error.value = err.message;
      } finally {
        loading.value = false;
      }
    }

    async function reloadReport() {
      if (!accountId.value) return;
      try {
        report.value = await api.report({
          model: model.value,
          from: fromDay.value,
          to: toDay.value,
        });
      } catch (err) {
        error.value = err.message;
      }
    }

    async function openJourney(uid) {
      selectedUid.value = uid;
      journeyLoading.value = true;
      try {
        journey.value = await api.journey(uid);
      } catch (err) {
        error.value = err.message;
        journey.value = null;
      } finally {
        journeyLoading.value = false;
      }
    }

    async function boot() {
      try {
        accounts.value = await api.accounts();
        if (!accounts.value.length) {
          error.value =
            'Demo tenant switching is disabled. Set CHANNELTRUTH_DEMO=1 for the standalone demo.';
          return;
        }
        accountId.value = accounts.value[0].id;
        session.accountId = accountId.value;
        await load();

        if (recent.value.length) {
          await openJourney(recent.value[0].conversion_uid);
        }
      } catch (err) {
        error.value = err.message;
      } finally {
        loading.value = false;
      }
    }

    onMounted(boot);

    return {
      accounts,
      accountId,
      fromDay,
      toDay,
      model,
      models,
      report,
      compare,
      recent,
      journey,
      selectedUid,
      error,
      loading,
      journeyLoading,
      totals,
      unattributed,
      MODEL_LABELS,
      MODEL_HINTS,
      money,
      percent,
      roas,
      load,
      reloadReport,
      openJourney,
    };
  },

  template: `
    <div :class="{ loading }">
      <header class="topbar">
        <div class="brand">
          <div class="brand-mark">CT</div>
          <div>
            <div class="brand-name">ChannelTruth</div>
            <div class="brand-sub">Multi-touch attribution &amp; ROAS</div>
          </div>
        </div>

        <div class="controls">
          <label class="field">
            <span>Account</span>
            <select v-model.number="accountId" @change="load" aria-label="Account">
              <option v-for="account in accounts" :key="account.id" :value="account.id">
                {{ account.name }}
              </option>
            </select>
          </label>
          <label class="field">
            <span>From</span>
            <input type="date" v-model="fromDay" @change="load" aria-label="From date" />
          </label>
          <label class="field">
            <span>To</span>
            <input type="date" v-model="toDay" @change="load" aria-label="To date" />
          </label>
          <label class="field">
            <span>Model</span>
            <select v-model="model" @change="reloadReport" aria-label="Attribution model">
              <option v-for="key in models" :key="key" :value="key">
                {{ MODEL_LABELS[key] }}
              </option>
            </select>
          </label>
        </div>
      </header>

      <main>
        <div v-if="error" class="banner">
          <span>{{ error }}</span>
          <button type="button" @click="load">Retry</button>
        </div>

        <section class="kpis" aria-label="Attribution totals">
          <div class="kpi">
            <div class="kpi-label">Attributed revenue</div>
            <div class="kpi-value">{{ money(totals ? totals.revenue_cents : 0) }}</div>
            <div class="kpi-foot">{{ totals ? totals.journeys : 0 }} conversions</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">Tracked spend</div>
            <div class="kpi-value">{{ money(totals ? totals.spend_cents : 0) }}</div>
            <div class="kpi-foot">all channels in range</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">Blended ROAS</div>
            <div class="kpi-value">{{ roas(totals ? totals.roas : null) }}</div>
            <div class="kpi-foot">
              {{ totals && totals.roas !== null && totals.roas < 1 ? 'below break-even' : 'revenue ÷ spend' }}
            </div>
          </div>
          <div class="kpi">
            <div class="kpi-label">Unattributed</div>
            <div class="kpi-value">{{ percent(unattributed / Math.max(totals ? totals.journeys : 1, 1), 1) }}</div>
            <div class="kpi-foot">{{ money(totals ? totals.unattributed_revenue_cents : 0) }} with no touch</div>
          </div>
        </section>

        <channel-table :rows="report ? report.channels : []" :model="model" :totals="totals" />

        <div style="margin-top: 16px">
          <model-matrix :compare="compare" :selected="model" />
        </div>

        <div style="margin-top: 16px">
          <journey-explorer
            :recent="recent"
            :journey="journey"
            :model="model"
            :loading="journeyLoading"
            @select="openJourney"
          />
        </div>

        <p class="num-sub" style="margin-top: 12px">{{ MODEL_HINTS[model] }}</p>
      </main>

      <footer class="app-footer">
        <span class="footer-brand">ChannelTruth</span>
        <span class="footer-rule"></span>
        <span>{{ compare ? compare.journeys : 0 }} journeys</span>
        <span>{{ models.length }} models</span>
        <span>{{ report ? report.channels.length : 0 }} channels</span>
        <span class="footer-gap"></span>
        <span class="footer-live" :class="{ 'is-down': error }">
          <i></i>{{ error ? 'API unreachable' : 'API connected' }}
        </span>
        <span class="footer-mono">{{ fromDay }} → {{ toDay }}</span>
      </footer>
    </div>
  `,
};

createApp(App).mount('#app');
