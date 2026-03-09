<template>
  <div class="th-filter-bar">
    <!-- Date Preset Selector -->
    <div class="th-tab-group">
      <button
        v-for="preset in presets"
        :key="preset.value"
        class="th-tab-btn"
        :class="{ active: filterStore.dateRange.preset === preset.value }"
        @click="filterStore.setPreset(preset.value)"
      >
        {{ preset.label }}
      </button>
    </div>

    <!-- Cross-filter Active Indicator -->
    <div v-if="crossFilterStore.hasFilters" class="flex items-center gap-2">
      <div
        v-for="filter in crossFilterStore.filterList"
        :key="filter.widgetId"
        class="inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-full"
        style="background: var(--th-brand-50); color: var(--th-brand-500)"
      >
        <span>{{ filter.label || filter.field }}: {{ filter.value }}</span>
        <button
          class="w-4 h-4 rounded-full flex items-center justify-center hover:bg-white/20 transition-colors"
          @click="crossFilterStore.clearFilter(filter.widgetId)"
        >
          <i class="fas fa-xmark text-[8px]"></i>
        </button>
      </div>
      <button
        class="text-[11px] font-medium px-2 py-1 rounded hover:bg-gray-100 transition-colors"
        style="color: var(--th-neutral)"
        @click="crossFilterStore.clearAll()"
      >
        Tümünü Temizle
      </button>
    </div>

    <!-- Spacer -->
    <div class="flex-1"></div>

    <!-- Right-side actions -->
    <slot name="actions" />
  </div>
</template>

<script setup>
import { useFilterStore } from '@/stores/dashboard/useFilterStore'
import { useCrossFilterStore } from '@/stores/dashboard/useCrossFilterStore'

const filterStore = useFilterStore()
const crossFilterStore = useCrossFilterStore()

const presets = [
  { value: '7d', label: '7G' },
  { value: '30d', label: '30G' },
  { value: '90d', label: '90G' },
  { value: '365d', label: '1Y' },
]
</script>
