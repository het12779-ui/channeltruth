import { MODEL_LABELS, money, percent, roas } from '../format.js';

export default {
  name: 'ChannelTable',
  props: {
    rows: { type: Array, default: () => [] },
    model: { type: String, default: 'linear' },
    totals: { type: Object, default: null },
  },
  methods: {
    money,
    percent,
    roas,
    modelLabel() {
      return MODEL_LABELS[this.model] || this.model;
    },
  },
  template: `
    <section class="panel" aria-labelledby="channels-title">
      <div class="panel-head">
        <div class="panel-title" id="channels-title">Channel credit</div>
        <div class="panel-meta">{{ modelLabel() }}</div>
      </div>

      <table v-if="rows.length">
        <thead>
          <tr>
            <th scope="col">Channel</th>
            <th scope="col">Attributed revenue</th>
            <th scope="col" style="min-width: 90px">Share</th>
            <th scope="col">Conversions</th>
            <th scope="col">Media spend</th>
            <th scope="col">ROAS</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.channel">
            <td><span class="chip">{{ row.channel }}</span></td>
            <td class="num">{{ money(row.revenue_cents) }}</td>
            <td>
              <div class="share-bar" :title="percent(row.share, 1)">
                <div class="share-fill" :style="{ width: (row.share * 100) + '%' }"></div>
              </div>
              <div class="num-sub">{{ percent(row.share, 1) }}</div>
            </td>
            <td class="num">{{ row.conversions.toFixed(1) }}</td>
            <td class="num">{{ money(row.spend_cents) }}</td>
            <td class="num" :style="{ color: row.roas !== null && row.roas < 1 ? 'var(--danger)' : 'inherit' }">
              {{ roas(row.roas) }}
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else class="empty">
        <strong>No conversions in this range</strong>
        Ingest events via <code>POST /api/v1/touchpoints</code> and <code>/conversions</code>.
      </div>

      <div v-if="rows.length" class="totals-row">
        <span>attributed <strong>{{ money(totals ? totals.revenue_cents : 0) }}</strong></span>
        <span>spend <strong>{{ money(totals ? totals.spend_cents : 0) }}</strong></span>
        <span>blended ROAS <strong>{{ roas(totals ? totals.roas : null) }}</strong></span>
      </div>
    </section>
  `,
};
