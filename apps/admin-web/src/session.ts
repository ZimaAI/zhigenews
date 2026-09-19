import { ref } from 'vue';
import { api, type AdminSession } from '@zhigenews/api-client';
export const session = ref<AdminSession | null>(null);
export const sessionError = ref('');
export async function loadSession() { session.value = await api<AdminSession>('getAdminSession'); return session.value; }
