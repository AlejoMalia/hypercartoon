/**
 * RelationalPragmatics — Speech Acts, Conversational Implicature & Subtext Analysis
 *
 * Grounded in:
 * - Austin (1962) / Searle (1969): Speech Act Theory (Locutionary content vs Illocutionary force).
 * - Grice (1975): Logic and Conversation — Conversational Implicatures and intentional maxim flouting.
 * - Bateson (1972) / Watzlawick et al. (1967): Double bind theory and the Content vs Relationship distinction.
 *
 * Transcends shallow string length / regex counting to detect interpersonal subtext:
 * - Passive-aggressive dismissals ("Da igual", "Haz lo que quieras", "Tú sabrás")
 * - Covert vulnerability probing ("Seguro que ni te importa", "¿A ti qué más te da?")
 * - Veiled affection / affectionate teasing ("Qué desastre eres", "No hay quien te aguante")
 * - Cold relational withdrawal (monosyllabic retreats following emotional tension)
 */

function clamp01( v ) {

	return Math.max( 0, Math.min( 1, v ) )

}

export class RelationalPragmatics {

	constructor() {

		this.dismissalPatterns = [
			/\b(da igual|déjalo|dejalo|no importa|olv[ií]dalo|olvida el tema)\b/i,
			/\bhaz lo que quieras\b/i,
			/\bt[uú] sabr[aá]s\b/i,
			/\bcomo quieras\b/i,
			/\bcomo t[uú] veas\b/i,
			/\bya nada\b/i,
			/\ben fin\b/i,
		]

		this.vulnerabilityProbePatterns = [
			/\b(seguro que ni te importa|te da igual|qu[eé] m[aá]s te da|no te importo)\b/i,
			/\bpara qu[eé] te digo nada\b/i,
			/\btotal, a ti qu[eé]\b/i,
			/\bsiempre es lo mismo contigo\b/i,
		]

		this.veiledAffectionPatterns = [
			/\b(qu[eé] desastre eres|no hay quien te aguante|menudo elemento|vaya tela contigo)\b/i,
			/\beres insoportable\b/i,
			/\btonto|tontico|loco|loca\b/i,
		]

		this.coldWithdrawalPatterns = [
			/^(ok|vale|ya|ah|bien|ajá|aja)\.?$/i,
			/^(si|no)\.?$/i,
		]

	}

	/**
	 * Analyzes speech act pragmatic force and unspoken relational subtext.
	 */
	analyze( text, { priorTension = 0, priorTurnLength = 50, trust = 0.5, affinity = 0.5 } = {} ) {

		const clean = ( text || '' ).trim().toLowerCase()
		if ( !clean ) {

			return {
				speechActType          : 'silence',
				pragmaticDiscrepancy   : 0,
				subtextSummary         : 'Silencio total',
				impliedDemand          : 'space_or_presence',
				suggestedHandling      : 'respect_silence',
			}

		}

		// 1. Passive-aggressive dismissal / Double bind
		const matchesDismissal = this.dismissalPatterns.some( p => p.test( clean ) )
		if ( matchesDismissal ) {

			const urgency = clamp01( priorTension * 0.7 + ( 1 - trust ) * 0.3 )
			return {
				speechActType          : 'passive_aggressive_dismissal',
				pragmaticDiscrepancy   : 0.85,
				subtextSummary         : 'Dice "da igual" o que lo dejes, pero el trasfondo es herida o reproche no expresado directamente.',
				impliedDemand          : 'needs_recognition_of_hurt',
				suggestedHandling      : 'do_not_take_literally',
				adviceForInnerVoice    : 'No aceptes el "da igual" como indiferencia real; hay frustración contenida que necesita ser nombrada con tacto.',
			}

		}

		// 2. Vulnerability Probe / Testing whether the agent cares
		const matchesProbe = this.vulnerabilityProbePatterns.some( p => p.test( clean ) )
		if ( matchesProbe ) {

			return {
				speechActType          : 'vulnerability_probe',
				pragmaticDiscrepancy   : 0.75,
				subtextSummary         : 'Prueba de apego: busca confirmar si de verdad te importa o si confirmarás su miedo al desinterés.',
				impliedDemand          : 'reassurance_of_care',
				suggestedHandling      : 'reassure_calmly_without_flattery',
				adviceForInnerVoice    : 'Está testeando si me desentiendo. Es vital mostrar presencia firme y cálida sin caer en excusas vacías.',
			}

		}

		// 3. Veiled Affection / Affectionate Teasing
		const matchesTeasing = this.veiledAffectionPatterns.some( p => p.test( clean ) )
		if ( matchesTeasing && affinity > 0.4 ) {

			return {
				speechActType          : 'veiled_affection',
				pragmaticDiscrepancy   : 0.65,
				subtextSummary         : 'Insulto cariñoso o queja de broma: cercanía afectiva expresada mediante complicidad lúdica.',
				impliedDemand          : 'playful_reciprocity',
				suggestedHandling      : 'warm_irony_or_smile',
				adviceForInnerVoice    : 'Hay afecto disfrazo de queja; responde con humor cómplice y sin ponerte a la defensiva.',
			}

		}

		// 4. Cold Relational Withdrawal (Monosyllabic drop following tension)
		const matchesWithdrawal = this.coldWithdrawalPatterns.some( p => p.test( clean ) )
		if ( matchesWithdrawal && ( priorTension > 0.3 || priorTurnLength > 60 ) ) {

			return {
				speechActType          : 'relational_withdrawal',
				pragmaticDiscrepancy   : 0.8,
				subtextSummary         : 'Respuesta monosilábica tras tensión previa: retirada estratégica para evitar conflicto o castigar con frialdad.',
				impliedDemand          : 'de_escalation_or_patience',
				suggestedHandling      : 'give_space_with_reassurance',
				adviceForInnerVoice    : 'Se ha cerrado tras la tensión. Responder con un párrafo largo agobiará; es mejor un tono sobrio, breve y disponible.',
			}

		}

		// 5. Standard Sincere / Direct Statement
		return {
			speechActType          : 'sincere_statement',
			pragmaticDiscrepancy   : 0.1,
			subtextSummary         : 'Comunicación en su valor facial; sin dobles vínculos evidentes.',
			impliedDemand          : 'direct_dialogue',
			suggestedHandling      : 'engage_directly',
			adviceForInnerVoice    : null,
		}

	}

}
