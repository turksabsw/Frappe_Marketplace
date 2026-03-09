<template>
  <div>
    <!-- Global Filter Bar -->
    <GlobalFilterBar>
      <template #actions>
        <button
          class="text-[11px] font-medium px-3 py-1.5 rounded-lg transition-colors"
          style="background: var(--th-brand-50); color: var(--th-brand-500)"
          @click="refreshAll"
        >
          <i class="fas fa-arrows-rotate text-[10px] mr-1"></i> Yenile
        </button>
      </template>
    </GlobalFilterBar>

    <!-- KPI Row -->
    <DashboardGrid>
      <KpiCard
        v-for="kpi in kpis"
        :key="kpi.title"
        v-bind="kpi"
        size="sm"
      />
    </DashboardGrid>

    <!-- Charts Row 1: Revenue Line + Order Status Donut -->
    <DashboardGrid class="mt-5">
      <WidgetWrapper title="Satış Performansı" subtitle="Son 12 aylık gelir trendi" size="xl">
        <template #actions>
          <div class="th-tab-group">
            <button
              v-for="tab in ['Aylık', 'Haftalık', 'Günlük']"
              :key="tab"
              class="th-tab-btn"
              :class="{ active: activeRevenueTab === tab }"
              @click="activeRevenueTab = tab"
            >
              {{ tab }}
            </button>
          </div>
        </template>
        <BaseChart :option="revenueOption" height="300px" @chart-click="onRevenueClick" />
      </WidgetWrapper>

      <WidgetWrapper title="Sipariş Dağılımı" subtitle="Bu ayki durum dağılımı" size="md">
        <BaseChart :option="donutOption" height="300px" @chart-click="onDonutClick" />
      </WidgetWrapper>
    </DashboardGrid>

    <!-- Charts Row 2: Category Bar + Heatmap -->
    <DashboardGrid class="mt-5">
      <WidgetWrapper title="Kategori Bazlı Satış" subtitle="En çok satan kategoriler" size="lg">
        <BaseChart :option="categoryOption" height="300px" />
      </WidgetWrapper>

      <WidgetWrapper title="Sipariş Yoğunluk Haritası" subtitle="Gün/saat bazlı sipariş yoğunluğu" size="lg">
        <BaseChart :option="heatmapOption" height="300px" />
      </WidgetWrapper>
    </DashboardGrid>

    <!-- Bottom Row: Table + RFQ + Activity -->
    <DashboardGrid class="mt-5">
      <!-- Orders Table -->
      <WidgetWrapper title="Son Siparişler" subtitle="Son 10 sipariş" size="xl" class="p-0 overflow-hidden">
        <template #actions>
          <router-link to="/app/Order" class="text-[11px] font-medium hover:opacity-80 transition-opacity" style="color: var(--th-brand-500)">
            Tümünü Gör <i class="fas fa-arrow-right text-[9px] ml-1"></i>
          </router-link>
        </template>

        <div class="overflow-x-auto">
          <table class="w-full">
            <thead><tr class="border-b" style="border-color: var(--th-surface-border)">
              <th class="tbl-th">Sipariş No</th>
              <th class="tbl-th">Müşteri</th>
              <th class="tbl-th">Tutar</th>
              <th class="tbl-th">Durum</th>
              <th class="tbl-th">Tarih</th>
            </tr></thead>
            <tbody>
              <tr v-for="order in recentOrders" :key="order.id" class="tbl-row border-b" style="border-color: var(--th-surface-border)">
                <td class="tbl-td font-semibold" style="color: var(--th-brand-500)">{{ order.id }}</td>
                <td class="tbl-td">{{ order.customer }}</td>
                <td class="tbl-td font-semibold" style="font-variant-numeric: tabular-nums">{{ order.amount }}</td>
                <td class="tbl-td">
                  <span class="badge" :class="getStatusClass(order.status)">{{ order.status }}</span>
                </td>
                <td class="tbl-td" style="color: var(--th-neutral)">{{ order.date }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </WidgetWrapper>

      <!-- RFQ Alerts + Activity -->
      <div class="th-widget-md space-y-5">
        <!-- RFQ Alerts -->
        <WidgetWrapper title="Bekleyen RFQ'lar">
          <template #actions>
            <span class="badge bg-red-50 text-red-600">{{ rfqAlerts.length }} Aktif</span>
          </template>
          <div class="space-y-2">
            <div
              v-for="rfq in rfqAlerts"
              :key="rfq.id"
              class="flex items-center gap-3 p-2.5 rounded-lg border transition-colors cursor-pointer hover:border-violet-200"
              style="background: var(--th-surface-elevated); border-color: var(--th-surface-border)"
              @click="openSlideOver(rfq)"
            >
              <div class="w-8 h-8 rounded flex items-center justify-center" :class="rfq.iconBg">
                <i class="fas fa-file-invoice text-xs" :class="rfq.iconColor"></i>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-xs font-semibold">{{ rfq.id }}</p>
                <p class="text-[10px] truncate" style="color: var(--th-neutral)">{{ rfq.detail }}</p>
              </div>
              <span class="text-[10px] font-bold whitespace-nowrap" :class="rfq.urgencyColor">{{ rfq.timeLeft }}</span>
            </div>
          </div>
        </WidgetWrapper>

        <!-- Activity Feed -->
        <WidgetWrapper title="Son Aktiviteler">
          <div class="relative">
            <div class="absolute left-[11px] top-2 bottom-2 w-px" style="background: var(--th-surface-border)"></div>
            <div class="space-y-4">
              <div v-for="act in activities" :key="act.text" class="flex gap-3 relative">
                <div class="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 z-10" :class="act.dotBg">
                  <i :class="[act.dotIcon, act.dotColor, 'text-[9px]']"></i>
                </div>
                <div>
                  <p class="text-xs" v-html="act.text"></p>
                  <p class="text-[10px] mt-0.5" style="color: var(--th-neutral)">{{ act.time }}</p>
                </div>
              </div>
            </div>
          </div>
        </WidgetWrapper>
      </div>
    </DashboardGrid>

    <!-- Charts Row 3: Scatter + Gauge -->
    <DashboardGrid class="mt-5">
      <WidgetWrapper title="Fiyat vs Satış Hacmi" subtitle="Ürün fiyat-hacim korelasyonu" size="lg">
        <BaseChart :option="scatterOption" height="300px" @chart-click="onScatterClick" />
      </WidgetWrapper>

      <WidgetWrapper title="Performans Göstergeleri" subtitle="Anlık KPI durumu" size="lg">
        <BaseChart :option="gaugeOption" height="300px" />
      </WidgetWrapper>
    </DashboardGrid>

    <!-- Slide-Over Panel -->
    <SlideOverPanel
      :visible="slideOverVisible"
      :title="slideOverTitle"
      :subtitle="slideOverSubtitle"
      @close="slideOverVisible = false"
    >
      <div v-if="slideOverData" class="space-y-4">
        <div v-for="(value, key) in slideOverData" :key="key" class="flex justify-between items-center py-2 border-b" style="border-color: var(--th-surface-border)">
          <span class="text-xs font-medium" style="color: var(--th-neutral)">{{ key }}</span>
          <span class="text-xs font-semibold">{{ value }}</span>
        </div>
      </div>
    </SlideOverPanel>
  </div>
</template>

<script setup>
import { ref, computed, shallowRef } from 'vue'
import DashboardGrid from '@/components/dashboard/layout/DashboardGrid.vue'
import WidgetWrapper from '@/components/dashboard/layout/WidgetWrapper.vue'
import KpiCard from '@/components/dashboard/widgets/KpiCard.vue'
import BaseChart from '@/components/dashboard/charts/BaseChart.vue'
import GlobalFilterBar from '@/components/dashboard/filters/GlobalFilterBar.vue'
import SlideOverPanel from '@/components/dashboard/layout/SlideOverPanel.vue'
import { STATUS_COLORS, MONTHS_TR, DAYS_TR, HOURS, CHART_PALETTE } from '@/constants/dashboard'

// ── Tab State ───────────────────────────────────────────────
const activeRevenueTab = ref('Aylık')

// ── Slide Over State ────────────────────────────────────────
const slideOverVisible = ref(false)
const slideOverTitle = ref('')
const slideOverSubtitle = ref('')
const slideOverData = ref(null)

function openSlideOver(item) {
  slideOverTitle.value = item.id || item.name || 'Detay'
  slideOverSubtitle.value = item.detail || ''
  slideOverData.value = {
    'Müşteri': item.detail?.split('·')[0]?.trim() || '-',
    'Kalem Sayısı': item.detail?.split('·')[1]?.trim() || '-',
    'Tahmini Tutar': item.detail?.split('·')[2]?.trim() || '-',
    'Kalan Süre': item.timeLeft || '-',
    'Durum': 'Beklemede',
    'Oluşturulma': '23.02.2026',
  }
  slideOverVisible.value = true
}

// ── KPI Data ────────────────────────────────────────────────
const kpis = [
  { title: 'Toplam Gelir', value: '₺2,847,390', icon: 'fas fa-turkish-lira-sign', iconBg: 'bg-violet-50', iconColor: 'text-violet-500', change: '18.4', changePositive: true },
  { title: 'Toplam Sipariş', value: '5,248', icon: 'fas fa-bag-shopping', iconBg: 'bg-blue-50', iconColor: 'text-blue-500', change: '12.1', changePositive: true },
  { title: 'Aktif Ürünler', value: '1,847', icon: 'fas fa-cube', iconBg: 'bg-amber-50', iconColor: 'text-amber-500', change: '5.7', changePositive: true },
  { title: 'Satıcı Puanı', value: '4.92 / 5.0', icon: 'fas fa-star', iconBg: 'bg-emerald-50', iconColor: 'text-emerald-500', change: '2.3', changePositive: true },
]

// ── Orders Table Data ───────────────────────────────────────
const recentOrders = [
  { id: '#ORD-7291', customer: 'Mega Yapı A.Ş.', amount: '₺124,500', status: 'Tamamlandı', date: '23.02.2026' },
  { id: '#ORD-7290', customer: 'Delta Kimya Ltd.', amount: '₺89,200', status: 'İşlemde', date: '23.02.2026' },
  { id: '#ORD-7289', customer: 'Atlas Metal San.', amount: '₺245,000', status: 'Tamamlandı', date: '22.02.2026' },
  { id: '#ORD-7288', customer: 'Yıldız Plastik', amount: '₺56,800', status: 'Beklemede', date: '22.02.2026' },
  { id: '#ORD-7287', customer: 'Ege Boya A.Ş.', amount: '₺178,300', status: 'Tamamlandı', date: '21.02.2026' },
]

function getStatusClass(status) {
  const s = STATUS_COLORS[status]
  return s ? `${s.bg} ${s.text}` : 'bg-gray-50 text-gray-600'
}

// ── RFQ Alerts ──────────────────────────────────────────────
const rfqAlerts = [
  { id: 'RFQ-2026-1204', detail: 'Mega Yapı A.Ş. · 12 kalem · ₺450K', timeLeft: '2 saat', urgencyColor: 'text-red-500', iconBg: 'bg-red-50', iconColor: 'text-red-500' },
  { id: 'RFQ-2026-1203', detail: 'Delta Kimya · 8 kalem · ₺180K', timeLeft: '1 gün', urgencyColor: 'text-amber-500', iconBg: 'bg-amber-50', iconColor: 'text-amber-500' },
  { id: 'RFQ-2026-1202', detail: 'Atlas Metal · 15 kalem · ₺290K', timeLeft: '3 gün', urgencyColor: 'text-gray-400', iconBg: 'bg-blue-50', iconColor: 'text-blue-500' },
]

// ── Activities ──────────────────────────────────────────────
const activities = [
  { text: 'Sipariş <b>#ORD-7291</b> tamamlandı', time: '5 dakika önce', dotBg: 'bg-emerald-100', dotIcon: 'fas fa-check', dotColor: 'text-emerald-500' },
  { text: 'Gönderi <b>#SHP-2891</b> yola çıktı', time: '23 dakika önce', dotBg: 'bg-blue-100', dotIcon: 'fas fa-truck', dotColor: 'text-blue-500' },
  { text: 'Yeni <b>5 yıldız</b> değerlendirme alındı', time: '1 saat önce', dotBg: 'bg-purple-100', dotIcon: 'fas fa-star', dotColor: 'text-purple-500' },
  { text: '<b>12 yeni ürün</b> onaylandı', time: '2 saat önce', dotBg: 'bg-amber-100', dotIcon: 'fas fa-box', dotColor: 'text-amber-500' },
]

// ── Chart Options (computed + shallowRef for performance) ──

const revenueOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { top: 20, right: 16, bottom: 24, left: 48 },
  xAxis: { type: 'category', data: MONTHS_TR },
  yAxis: { type: 'value', axisLabel: { formatter: '₺{value}K' } },
  series: [{
    type: 'line',
    data: [180, 210, 195, 245, 230, 280, 260, 310, 340, 290, 365, 420],
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: { width: 2.5 },
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(108,93,211,0.15)' },
          { offset: 1, color: 'rgba(108,93,211,0)' },
        ],
      },
    },
  }],
  animationDuration: 1000,
  animationEasing: 'cubicOut',
}))

const donutOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, itemWidth: 10, itemHeight: 10 },
  series: [{
    type: 'pie',
    radius: ['52%', '78%'],
    center: ['50%', '42%'],
    avoidLabelOverlap: false,
    itemStyle: { borderRadius: 6, borderColor: 'var(--th-surface-card)', borderWidth: 3 },
    label: {
      show: true, position: 'center',
      formatter: '{total|1,833}\n{sub|Toplam Sipariş}',
      rich: {
        total: { fontSize: 26, fontWeight: 800, lineHeight: 32 },
        sub: { fontSize: 11, color: '#9ca3af', lineHeight: 18 },
      },
    },
    emphasis: { label: { show: true }, scaleSize: 6 },
    data: [
      { value: 1248, name: 'Tamamlanan', itemStyle: { color: '#10b981' } },
      { value: 384, name: 'İşlemde', itemStyle: { color: '#3b82f6' } },
      { value: 128, name: 'Beklemede', itemStyle: { color: '#f59e0b' } },
      { value: 73, name: 'İptal', itemStyle: { color: '#ef4444' } },
    ],
  }],
  animationDuration: 1000,
}))

const categoryOption = computed(() => {
  const cats = ['Solventler', 'Reçineler', 'Yapıştırıcılar', 'Boyalar', 'Hammadde', 'Ambalaj']
  const vals = [486, 342, 278, 224, 198, 156]
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (p) => p[0].name + '<br/><b>₺' + p[0].value + 'K</b>',
    },
    grid: { top: 10, right: 30, bottom: 10, left: 8, containLabel: true },
    xAxis: { type: 'value', axisLabel: { formatter: '{value}K' } },
    yAxis: { type: 'category', data: cats, inverse: true },
    series: [{
      type: 'bar',
      data: vals,
      barWidth: 16,
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: (p) => CHART_PALETTE[p.dataIndex % CHART_PALETTE.length],
      },
      label: { show: true, position: 'right', formatter: '₺{c}K', fontSize: 10, fontWeight: 600 },
    }],
    animationDuration: 800,
  }
})

const heatmapOption = computed(() => {
  const data = []
  for (let i = 0; i < DAYS_TR.length; i++) {
    for (let j = 0; j < HOURS.length; j++) {
      const base = (i < 5) ? 20 : 8
      const peak = (j >= 2 && j <= 5) ? 30 : 10
      data.push([j, i, Math.floor(Math.random() * (base + peak) + 5)])
    }
  }
  return {
    tooltip: {
      position: 'top',
      formatter: (p) => DAYS_TR[p.data[1]] + ' ' + HOURS[p.data[0]] + '<br/><b>' + p.data[2] + ' sipariş</b>',
    },
    grid: { top: 10, right: 16, bottom: 36, left: 40 },
    xAxis: { type: 'category', data: HOURS, splitArea: { show: false } },
    yAxis: { type: 'category', data: DAYS_TR, splitArea: { show: false } },
    visualMap: {
      min: 0, max: 55, calculable: false, orient: 'horizontal', left: 'center', bottom: 0,
      itemWidth: 12, itemHeight: 100,
      inRange: { color: ['#f0edff', '#c4b5fd', '#8b7fe8', '#6c5dd3', '#4c3db3'] },
    },
    series: [{
      type: 'heatmap', data,
      label: { show: false },
      itemStyle: { borderRadius: 3, borderColor: 'var(--th-surface-card)', borderWidth: 2 },
      emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(108,93,211,0.3)' } },
    }],
    animationDuration: 600,
  }
})

const scatterOption = computed(() => {
  const genData = (count) => Array.from({ length: count }, () => [
    Math.random() * 900 + 50,
    Math.random() * 300 + 20,
    Math.random() * 40 + 10,
  ])
  return {
    tooltip: {
      formatter: (p) => 'Fiyat: ₺' + p.data[0].toFixed(0) + '<br/>Hacim: ' + p.data[1].toFixed(0) + ' adet',
    },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 10 },
    grid: { top: 32, right: 16, bottom: 24, left: 48 },
    xAxis: { name: 'Fiyat (₺)', nameTextStyle: { fontSize: 10 } },
    yAxis: { name: 'Satış Hacmi', nameTextStyle: { fontSize: 10 } },
    series: [
      { name: 'Solventler', type: 'scatter', data: genData(18), symbolSize: (d) => d[2], itemStyle: { color: 'rgba(108,93,211,0.6)', borderColor: '#6c5dd3', borderWidth: 1 } },
      { name: 'Reçineler', type: 'scatter', data: genData(14), symbolSize: (d) => d[2], itemStyle: { color: 'rgba(59,130,246,0.6)', borderColor: '#3b82f6', borderWidth: 1 } },
      { name: 'Yapıştırıcılar', type: 'scatter', data: genData(12), symbolSize: (d) => d[2], itemStyle: { color: 'rgba(16,185,129,0.6)', borderColor: '#10b981', borderWidth: 1 } },
    ],
    animationDuration: 800,
  }
})

const gaugeOption = computed(() => ({
  series: [
    {
      type: 'gauge', center: ['25%', '55%'], radius: '70%',
      startAngle: 200, endAngle: -20, min: 0, max: 100,
      axisLine: { lineStyle: { width: 12, color: [[0.3, '#ef4444'], [0.7, '#f59e0b'], [1, '#10b981']] } },
      axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { distance: 12, fontSize: 9 },
      pointer: { length: '60%', width: 4, itemStyle: { color: '#6c5dd3' } },
      anchor: { show: true, size: 8, itemStyle: { color: '#6c5dd3', borderColor: 'var(--th-surface-card)', borderWidth: 2 } },
      title: { show: true, offsetCenter: [0, '72%'], fontSize: 11, fontWeight: 600 },
      detail: { valueAnimation: true, fontSize: 22, fontWeight: 800, offsetCenter: [0, '45%'], formatter: '{value}%' },
      data: [{ value: 78, name: 'Teslimat Oranı' }],
    },
    {
      type: 'gauge', center: ['75%', '55%'], radius: '70%',
      startAngle: 200, endAngle: -20, min: 0, max: 5,
      axisLine: { lineStyle: { width: 12, color: [[0.4, '#ef4444'], [0.7, '#f59e0b'], [1, '#10b981']] } },
      axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { distance: 12, fontSize: 9 },
      pointer: { length: '60%', width: 4, itemStyle: { color: '#6c5dd3' } },
      anchor: { show: true, size: 8, itemStyle: { color: '#6c5dd3', borderColor: 'var(--th-surface-card)', borderWidth: 2 } },
      title: { show: true, offsetCenter: [0, '72%'], fontSize: 11, fontWeight: 600 },
      detail: { valueAnimation: true, fontSize: 22, fontWeight: 800, offsetCenter: [0, '45%'], formatter: '{value}' },
      data: [{ value: 4.92, name: 'Müşteri Puanı' }],
    },
  ],
  animationDuration: 1200,
  animationEasing: 'elasticOut',
}))

// ── Chart Event Handlers ────────────────────────────────────
function onRevenueClick(params) {
  console.log('[Revenue Click]', params)
}
function onDonutClick(params) {
  console.log('[Donut Click]', params.name, params.value)
}
function onScatterClick(params) {
  console.log('[Scatter Click]', params)
}
function refreshAll() {
  // Will be connected to useDashboardData.refresh() when API is live
  console.log('[Dashboard] Refresh all widgets')
}
</script>
