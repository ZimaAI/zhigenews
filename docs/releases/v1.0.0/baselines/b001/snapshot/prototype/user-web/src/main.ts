import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import '@shared/styles.css';
import './user-tokens.css';
import './user.css';
createApp(App).use(router).mount('#app');
