<template>
  <header class="sticky top-0 z-30 bg-white border-b border-[#e8e8ef] h-[56px] flex items-center px-4 xl:px-5 gap-3">
    <!-- Hamburger: visible when panel is collapsed -->
    <button
      v-if="!sidebar.panelVisible"
      class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors flex-shrink-0"
      @click="sidebar.togglePanel()"
    >
      <i class="fas fa-bars text-sm"></i>
    </button>

    <!-- Search Bar -->
    <div class="relative flex-1 max-w-[200px] sm:max-w-[280px] lg:max-w-[380px] xl:max-w-[540px]">
      <i class="fas fa-magnifying-glass absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-[13px]"></i>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Herşeyi Ara..."
        class="w-full h-[38px] lg:h-[42px] pl-11 pr-4 text-[13px] bg-gray-50/80 border border-gray-200 rounded-full outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-500/10 focus:bg-white transition-all placeholder:text-gray-400"
        @focus="showSearchResults = true"
        @blur="hideSearchResults"
        @keydown.escape="showSearchResults = false"
      >
      <!-- Search Results -->
      <GlobalSearch
        v-if="showSearchResults && searchQuery.length >= 2"
        :query="searchQuery"
        @select="handleSearchSelect"
      />
    </div>

    <!-- Spacer -->
    <div class="flex-1"></div>

    <!-- Right Icons -->
    <div class="flex items-center gap-0.5">

      <!-- Notifications -->
      <button class="hdr-icon-btn relative" @click.stop="handleNotificationClick" title="Bildirimler">
        <i class="fas fa-bell text-[15px]"></i>
        <span
          v-if="notifications.hasUnread"
          class="absolute top-1.5 right-1.5 w-2 h-2 bg-green-500 rounded-full ring-2 ring-white"
        ></span>
      </button>


      <!-- Quick Links -->
      <div class="relative">
        <button class="hdr-icon-btn" @click.stop="toggleQuickLinks" title="Quick Links">
          <i class="fas fa-grip text-[15px]"></i>
        </button>
        <Transition name="dropdown">
          <div
            v-if="activeOverlay === 'headerQuickLinks'"
            class="absolute top-[calc(100%+8px)] right-0 w-[300px] bg-white border border-gray-200 rounded-lg shadow-2xl shadow-black/12 z-[60] overflow-hidden"
            @click.stop
          >
            <div class="flex flex-col items-center justify-center py-5 bg-gradient-to-r from-violet-600 to-indigo-700 relative">
              <h3 class="text-white font-semibold text-sm">Quick Links</h3>
              <span class="inline-block mt-1.5 text-[10px] bg-white/20 text-white px-2.5 py-0.5 rounded-md font-medium">Hızlı Erişim</span>
            </div>
            <div class="grid grid-cols-2">
              <a href="#" class="flex flex-col items-center gap-2 py-5 border-r border-b border-gray-100 hover:bg-gray-50 transition-colors" @click.prevent="navigateTo('/app/accounting')">
                <div class="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center"><i class="fas fa-file-invoice-dollar text-violet-600 text-lg"></i></div>
                <div class="text-center"><p class="text-xs font-semibold text-gray-800">Muhasebe</p><p class="text-[10px] text-gray-400">Hesaplar</p></div>
              </a>
              <a href="#" class="flex flex-col items-center gap-2 py-5 border-b border-gray-100 hover:bg-gray-50 transition-colors" @click.prevent="navigateTo('/app/admin')">
                <div class="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center"><i class="fas fa-shield-halved text-violet-600 text-lg"></i></div>
                <div class="text-center"><p class="text-xs font-semibold text-gray-800">Yönetim</p><p class="text-[10px] text-gray-400">Konsol</p></div>
              </a>
              <a href="#" class="flex flex-col items-center gap-2 py-5 border-r border-gray-100 hover:bg-gray-50 transition-colors" @click.prevent="navigateTo('/app/projects')">
                <div class="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center"><i class="fas fa-folder-open text-violet-600 text-lg"></i></div>
                <div class="text-center"><p class="text-xs font-semibold text-gray-800">Projeler</p><p class="text-[10px] text-gray-400">Görevler</p></div>
              </a>
              <a href="#" class="flex flex-col items-center gap-2 py-5 hover:bg-gray-50 transition-colors" @click.prevent="navigateTo('/app/support')">
                <div class="w-10 h-10 rounded-xl bg-violet-50 flex items-center justify-center"><i class="fas fa-headset text-violet-600 text-lg"></i></div>
                <div class="text-center"><p class="text-xs font-semibold text-gray-800">Destek</p><p class="text-[10px] text-gray-400">Talepler</p></div>
              </a>
            </div>
            <div class="px-4 py-2.5 border-t border-gray-100 text-center">
              <a href="#" class="text-xs font-medium text-gray-400 hover:text-violet-600 transition-colors" @click.prevent="navigateTo('/dashboard')">
                Tümünü Gör <i class="fas fa-chevron-right text-[8px] ml-0.5"></i>
              </a>
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSidebarStore } from '@/stores/sidebar'
import { useNotificationStore } from '@/stores/notification'
import { useOverlay } from '@/composables/useOverlay'
import GlobalSearch from '@/components/common/GlobalSearch.vue'

const router = useRouter()
const sidebar = useSidebarStore()
const notifications = useNotificationStore()
const { active: activeOverlay, toggle: toggleOverlay, close: closeOverlays } = useOverlay()

const searchQuery = ref('')
const showSearchResults = ref(false)

function handleNotificationClick() {
  toggleOverlay('notifications')
}

function toggleQuickLinks() {
  toggleOverlay('headerQuickLinks')
}

function navigateTo(path) {
  closeOverlays()
  router.push(path)
}

function hideSearchResults() {
  setTimeout(() => { showSearchResults.value = false }, 200)
}

function handleSearchSelect(item) {
  searchQuery.value = ''
  showSearchResults.value = false
}

function handleOutsideClick(e) {
  if (!e.target.closest('.hdr-icon-btn') &&
      !e.target.closest('#notificationPanel') &&
      !e.target.closest('.rail-icon') &&
      !e.target.closest('.rail-avatar-btn') &&
      !e.target.closest('[class*="absolute bottom"]')) {
    closeOverlays()
  }
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
})

onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
})
</script>
