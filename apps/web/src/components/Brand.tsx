import { Blocks } from 'lucide-react'
import { useI18n } from '../i18n/context'

export function Brand({ compact = false }: { compact?: boolean }) {
  const { t } = useI18n()
  return (
    <div className={`brand ${compact ? 'brand--compact' : ''}`}>
      <span className="brand__mark"><Blocks size={20} strokeWidth={2.2} /></span>
      {!compact && <span><strong>{t('product')}</strong><small>{t('tagline')}</small></span>}
    </div>
  )
}
