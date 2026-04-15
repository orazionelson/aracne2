import { onMounted, onUnmounted } from 'vue'
import { useUiConfigStore } from '@/stores/ui_config'

const LINK_ID = 'public-custom-css-propagated'
const CSS_URL = '/api/v1/settings/homepage-css/file'

/**
 * Inject the custom homepage CSS into <head> for non-homepage public views
 * when both conditions are met:
 *   - a custom CSS file has been uploaded (has_custom_homepage_css)
 *   - the "Propagate Custom CSS" setting is enabled (home_propagate_css)
 *
 * The <link> element is appended on mount and removed on unmount so it does
 * not leak into admin or other non-public routes.
 */
export function usePublicCustomCss(): void {
  const uiConfig = useUiConfigStore()

  onMounted(() => {
    if (!uiConfig.config.has_custom_homepage_css || !uiConfig.config.home_propagate_css) return
    if (document.getElementById(LINK_ID)) return   // already injected (HMR safety)
    const link = document.createElement('link')
    link.rel  = 'stylesheet'
    link.href = CSS_URL
    link.id   = LINK_ID
    document.head.appendChild(link)
  })

  onUnmounted(() => {
    document.getElementById(LINK_ID)?.remove()
  })
}
