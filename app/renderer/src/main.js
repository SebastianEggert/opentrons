import Vue from 'vue'
import VueRouter from 'vue-router'
import VueResource from 'vue-resource'
import { Toast } from 'vuex-toast'
import store from './store/store'
import {
  Home,
  StepList,
  Upload,
  Connect,
  Placeable,
  Instrument,
  Run
} from './components/export'


Vue.use(VueRouter)
Vue.use(VueResource)
Vue.component('StepList', StepList)
Vue.component('Toast', Toast)

const routes = [
  { path: '/connect', component: Connect },
  { path: '/upload', component: Upload },
  { path: '/calibrate/:instrument', component: Instrument },
  { path: '/calibrate/:instrument/:placeable', component: Placeable },
  { path: '/run', component: Run },
  { path: '*', redirect: "/connect" },
]

const router = new VueRouter({
  routes
})

window.onload = function() {
  const app = new Vue({
    router,
    store,
    ...Home
  }).$mount('#app')
}
