<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Leaf, LayoutDashboard, Radio, Activity, FlaskConical, Users, Send, Menu, LogOut, Settings } from 'lucide-vue-next';
import Modal from '@ui/Modal.vue';
import EmptyState from '@ui/EmptyState.vue';
import { request, errorText, toast, notify } from './lib';
import { session, sessionError, loadSession } from './session';
const route = useRoute(); const router = useRouter(); const menu = ref(false); const busy = ref(false);
const nav = [
  { path: '/overview', label: '概览', icon: LayoutDashboard }, { path: '/sources', label: '新闻来源', icon: Radio },
  { path: '/runs', label: '运行观察', icon: Activity }, { path: '/evaluations', label: '评估实验', icon: FlaskConical },
  { path: '/users', label: '匿名账户', icon: Users }, { path: '/deliveries', label: '投递记录', icon: Send },
];
const title = computed(() => nav.find(item => route.path.startsWith(item.path))?.label || '管理控制台');
watch(() => route.path, () => { menu.value = false; });
async function logout() { busy.value = true; try { await request('adminLogout'); session.value = null; await router.push('/login'); } catch (error) { notify(errorText(error)); } finally { busy.value = false; } }
async function retrySession() { busy.value = true; try { await loadSession(); sessionError.value = ''; } catch (error) { sessionError.value = errorText(error); } finally { busy.value = false; } }
</script>
<template>
  <div class="app-shell--admin">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <template v-if="route.path !== '/login'">
      <aside class="sidebar" aria-label="管理导航">
        <RouterLink class="brand" to="/overview" aria-label="知更管理概览"><span class="brand-mark"><Leaf :size="23" aria-hidden="true" /></span><span class="brand-name">知更<span>ZHIGE NEWS</span></span></RouterLink>
        <div class="sidebar-section-label">管理工作台</div>
        <nav class="desktop-nav"><RouterLink v-for="item in nav" :key="item.path" :to="item.path" :class="{ selected: route.path.startsWith(item.path) }" :aria-current="route.path.startsWith(item.path) ? 'page' : undefined" :title="item.label" :aria-label="item.label"><component :is="item.icon" :size="19" aria-hidden="true" /><span>{{ item.label }}</span></RouterLink></nav>
        <div class="sidebar-note"><Settings :size="19" aria-hidden="true" /><strong>让信息有据可查</strong><p>来源、运行与发布状态<br>汇聚在同一工作台。</p></div>
        <div class="sidebar-account"><span class="avatar" aria-hidden="true">管</span><div><strong>{{ session?.name || '管理员' }}</strong><p>管理控制台</p></div><button class="icon-button" :disabled="busy" aria-label="退出登录" title="退出登录" @click="logout"><LogOut :size="18" /></button></div>
      </aside>
      <div class="app-body">
        <header class="topbar"><div class="row"><button class="icon-button menu-toggle" aria-label="打开管理菜单" @click="menu = true"><Menu :size="20" /></button><span class="topbar-product">知更管理控制台</span><span class="breadcrumb-divider">/</span><strong class="topbar-title">{{ title }}</strong></div><span class="meta">Asia/Shanghai</span></header>
        <main id="main-content" class="main-content" tabindex="-1"><EmptyState v-if="sessionError" title="暂时无法验证管理会话" :description="sessionError" error><button class="button button--primary" :disabled="busy" @click="retrySession">{{ busy ? '正在重试…' : '重试连接' }}</button><RouterLink class="button" to="/login">前往登录</RouterLink></EmptyState><RouterView v-else-if="session" /><p v-else role="status" class="muted">正在验证管理会话…</p></main>
        <footer class="app-footer"><span>知更 · 管理控制台</span><span>v1.0.0 · 时间：Asia/Shanghai</span></footer>
      </div>
    </template>
    <main v-else id="main-content" class="admin-login-container" tabindex="-1"><RouterView /></main>
    <Modal :open="menu" title="管理菜单" @close="menu = false"><nav class="mobile-menu"><RouterLink v-for="item in nav" :key="item.path" :to="item.path" :aria-current="route.path.startsWith(item.path) ? 'page' : undefined"><component :is="item.icon" :size="19" aria-hidden="true" />{{ item.label }}</RouterLink></nav><template #footer><button class="button" :disabled="busy" @click="logout"><LogOut :size="16" />退出登录</button></template></Modal>
    <div v-if="toast" class="toast" role="status">{{ toast }}<button class="icon-button" aria-label="关闭通知" @click="toast = ''">×</button></div>
  </div>
</template>
