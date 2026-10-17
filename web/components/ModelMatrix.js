import { MODEL_LABELS, compact, money } from '../format.js';

export default {
  name: 'ModelMatrix',
  props: {
    compare: { type: Object, default: null },
    selected: { type: String, default: 'linear' },
  },
  computed: {
    maxTotal() {
      if (!this.compare) return 1;
      return Math.max(1, ...Object.values(this.compare.total_by_model));
    },
  },
  methods: {
    compact,
    money,
    label(model) {
      return MODEL_LABELS[model] || model;
    },
    intensity(row, model) {
      const share = row.share_by_model[model] || 0;
      return { background: `rgba(167, 139, 250, ${(0.04 + share * 0.32).toFixed(3)})` };
    },
    delta(row) {
      // How much this model moves the channel versus last-touch, the number
      // every platform reports by default.
      const base = row.revenue_by_model.last_touch || 0;
      const value = row.revenue_by_model[this.selected] || 0;
      if (base === 0 && value === 0) return null;
      if (base === 0) return 'new';
      return `${value >= base ? '+' : '−'}${Math.abs(((value - base) / base) * 100).toFixed(0)}%`;
    },
    isPositive(row) {
      return (row.revenue_by_model[this.selected] || 0) >= (row.revenue_by_model.last_touch || 0);
    },
  },
  template: `
    <section class="panel" aria-labelledby="matrix-title">
      <div class="panel-head">
        <div class="panel-title" id="matrix-title">Model comparison</div>
        <div class="panel-meta">{{ compare ? compare.journeys : 0 }} journeys</div>
      </div>

      <div v-if="compare && compare.channels.length" class="matrix-wrap">
        <table class="matrix">
          <thead>
            <tr>
              <th scope="col">Channel</th>
              <th
                v-for="model in compare.models"
                :key="model"
                scope="col"
                class="model-head"
                :class="{ 'is-selected': model === selected }"
              >
                {{ label(model) }}
              </th>
              <th scope="col" class="model-head" title="Change versus last-touch">vs last</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in compare.channels" :key="row.channel">
              <td><span class="chip">{{ row.channel }}</span></td>
              <td
                v-for="model in compare.models"
                :key="model"
                class="money"
                :class="{ 'is-selected': model === selected }"
                :style="intensity(row, model)"
                :title="money(row.revenue_by_model[model])"
              >
                {{ compact(row.revenue_by_model[model]) }}
              </td>
              <td class="money">
                <span v-if="delta(row) === null" style="color: var(--faint)">—</span>
                <span
                  v-else-if="delta(row) === 'new'"
                  style="color: var(--ok); font-family: var(--mono); font-size: 11px"
                >new</span>
                <span
                  v-else
                  :style="{ color: isPositive(row) ? 'var(--ok)' : 'var(--danger)', fontFamily: 'var(--mono)', fontSize: '11px' }"
                >{{ delta(row) }}</span>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td style="color: var(--faint); font-size: 11px">total</td>
              <td v-for="model in compare.models" :key="model" class="money num">
                {{ compact(compare.total_by_model[model]) }}
              </td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div v-else class="empty">
        <strong>Nothing to compare yet</strong>
        Load a date range that contains conversions.
      </div>

      <div class="formula">
        Every model distributes the same revenue pool. If the totals ever differ,
        the allocation is wrong — that invariant is asserted in the test suite.
      </div>
    </section>
  `,
};
