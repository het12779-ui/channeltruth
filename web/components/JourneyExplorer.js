import { MODEL_LABELS, dateTime, money, moneyExact, shortDate } from '../format.js';

export default {
  name: 'JourneyExplorer',
  props: {
    recent: { type: Array, default: () => [] },
    journey: { type: Object, default: null },
    model: { type: String, default: 'linear' },
    loading: { type: Boolean, default: false },
  },
  emits: ['select'],
  methods: {
    money,
    moneyExact,
    shortDate,
    dateTime,
    label(model) {
      return MODEL_LABELS[model] || model;
    },
    creditFor(touch) {
      return touch.credits_by_model[this.model] || 0;
    },
    weightFor(touch) {
      return touch.weight_by_model[this.model] || 0;
    },
  },
  template: `
    <section class="panel" aria-labelledby="journey-title">
      <div class="panel-head">
        <div class="panel-title" id="journey-title">Journey explorer</div>
        <div class="panel-meta">{{ label(model) }} credit</div>
      </div>

      <div class="journey-grid">
        <div class="journey-list" role="list">
          <button
            v-for="row in recent"
            :key="row.conversion_uid"
            class="journey-item"
            :class="{ 'is-active': journey && journey.conversion_uid === row.conversion_uid }"
            type="button"
            role="listitem"
            @click="$emit('select', row.conversion_uid)"
          >
            <span>
              <span class="uid">{{ row.conversion_uid }}</span>
              <div class="num-sub">{{ shortDate(row.occurred_at.slice(0, 10)) }}</div>
            </span>
            <span class="rev">{{ money(row.revenue_cents) }}</span>
          </button>

          <div v-if="!recent.length" class="empty">
            <strong>No conversions yet</strong>
            Ingest a conversion to inspect its path.
          </div>
        </div>

        <div class="journey-detail">
          <template v-if="journey">
            <div style="display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap">
              <span style="font-size: 15px; font-weight: 650">{{ money(journey.revenue_cents) }}</span>
              <span class="drawer-sub">{{ journey.conversion_uid }}</span>
            </div>
            <div class="num-sub" style="margin-top: 3px">
              {{ dateTime(journey.occurred_at) }} · {{ journey.touches.length }} touches in a
              {{ journey.lookback_days }}-day lookback
            </div>

            <ul class="timeline">
              <li v-for="touch in journey.touches" :key="touch.touchpoint_id">
                <div class="touch-head">
                  <span class="chip">{{ touch.channel }}</span>
                  <span class="touch-time">{{ dateTime(touch.occurred_at) }}</span>
                  <span class="touch-credit">{{ money(creditFor(touch)) }}</span>
                </div>
                <div class="touch-bar">
                  <span :style="{ width: (weightFor(touch) * 100) + '%' }"></span>
                </div>
                <div class="touch-weight">
                  {{ touch.kind }} · {{ (weightFor(touch) * 100).toFixed(1) }}% of credit
                </div>
              </li>

              <li class="conversion-marker">
                <div class="touch-head">
                  <span class="touch-channel">Conversion</span>
                  <span class="touch-time">{{ dateTime(journey.occurred_at) }}</span>
                  <span class="touch-credit" style="color: var(--ok)">
                    {{ money(journey.revenue_cents) }}
                  </span>
                </div>
              </li>
            </ul>

            <div class="totals-row">
              <span
                v-for="(cents, modelKey) in journey.totals_by_model"
                :key="modelKey"
                :style="{ color: modelKey === model ? 'var(--accent)' : 'inherit' }"
              >
                {{ label(modelKey) }} <strong>{{ money(cents) }}</strong>
              </span>
            </div>
          </template>

          <div v-else class="empty">
            <strong>Select a conversion</strong>
            Pick a journey on the left to see how each model splits its revenue.
          </div>
        </div>
      </div>
    </section>
  `,
};
