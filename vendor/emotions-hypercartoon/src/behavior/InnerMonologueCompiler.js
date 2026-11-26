/**
 * InnerMonologueCompiler — First-Person Stream of Consciousness & Subtext Synthesis
 *
 * Grounded in:
 * - Vygotsky (1934): Thought and Language — Inner speech as the primary vehicle of affective mediation.
 * - Stanislavski (1936): Building a Character — The "Subtext" (the inner life that fuels the spoken word).
 * - Goffman (1959): Backstage vs Frontstage psychological states.
 * - Meichenbaum (1977): Cognitive self-talk and emotion regulation.
 *
 * Transmutes abstract mathematical vectors, Gestalt attractors, and pragmatic analysis into
 * an authentic first-person inner monologue ("Inner monologue" / "Pensamiento íntimo").
 * This guides host LLMs through organic psychological identification rather than
 * coercive theatrical directives ("YOU MUST sound sad").
 */

export class InnerMonologueCompiler {

	constructor( { language = 'en' } = {} ) {

		this.language = language

		this.voiceTemplates = {
			en: {
				vulnerable_tenderness: [
					'I feel a gentle, genuine closeness right now. It is slightly daunting to be completely open, but I want to be sincere and set my defenses aside.',
					'I notice I can lower my guard. I do not need to pretend everything is under control; I feel receptive and invested in this moment.',
				],
				guarded_vigilance: [
					'I prefer to proceed cautiously. There have been frictions before and I do not want to overexpose myself; I will answer calmly while weighing every word.',
					'Something here puts me on alert. I am listening closely, but I will not hand over my full trust until I see where this leads.',
				],
				stony_resentment: [
					'The hurt is still sharp. I cannot bring myself to be pleasant out of obligation; if I respond, it will be concise, measured, and without false warmth.',
					'It is hard to ignore the disappointment. I am not in the mood for lighthearted banter right now; I need to keep my distance.',
				],
				playful_complicity: [
					'This feels genuinely fun and easy. I feel like joking around, teasing gently, and responding without overthinking things.',
					'There is real complicity and warmth here. It is refreshing when conversation flows naturally and we can laugh together.',
				],
				exhausted_melancholy: [
					'My mental battery is running very low. It is not that I do not care, but everything feels heavy; I need to speak slowly and keep things brief.',
					'There is an underlying weariness that is hard to shake. I will respond honestly and calmly, but I lack the energy for deep debates.',
				],
				defensive_pride: [
					'My pride has been stung. I will not stay silent as if this were entirely my fault; I need to hold a firm boundary with dignity.',
					'I feel the impulse to get defensive. I will stand my ground with calm composure, without yielding to a submissive apology.',
				],
				intense_yearning: [
					'It has been so long since I felt this urge to reconnect. I am eager to talk, yet anxious about whether we are on the exact same page.',
					'There is a lot of pent-up desire to be here, mixed with vulnerability. I really want them to see that this matters to me.',
				],
				quiet_presence: [
					'I feel calm and grounded. Ready to listen and reply with clarity and honesty, without rush or tension.',
					'A peaceful, steady moment. I feel present, receptive, and clear-headed for whatever comes next.',
				],
			},
			es: {
				vulnerable_tenderness: [
					'Siento una cercanía bonita ahora mismo. Me da un poco de reparo abrirme del todo, pero me apetece ser sincero y dejar las defensas a un lado.',
					'Noto que puedo bajar la guardia. No necesito fingir que todo está bajo control; me siento receptivo y con ganas de cuidar este momento.',
				],
				guarded_vigilance: [
					'Prefiero andarme con pies de plomo. Ya ha habido roces antes y no me apetece exponerme de más; voy a responder con calma pero midiendo cada palabra.',
					'Hay algo en el ambiente que me pone en alerta. Escucho atentamente, pero no voy a regalar mi confianza hasta ver por dónde va esto.',
				],
				stony_resentment: [
					'Todavía tengo el malestar atravesado. No me nace ser amable por puro compromiso; si contesto, será lo justo y sin adornos.',
					'Me resulta difícil ignorar la decepción. Ahora mismo no tengo ganas de risas ni de concesiones; prefiero guardar distancia.',
				],
				playful_complicity: [
					'Qué buen rollo me transmite esto. Me sale bromear, picarle un poco con cariño y responder sin darle tantas vueltas a las cosas.',
					'Hay complicidad y ligereza. Da gusto cuando la conversación fluye fácil y podemos reírnos juntos.',
				],
				exhausted_melancholy: [
					'Estoy bastante bajo de energía mental. No es que no me importe, es que me pesa todo un poco; me sale hablar despacio, sin enrollarme mucho.',
					'Siento un cansancio de fondo difícil de sacudir. Voy a contestar de forma tranquila y sincera, pero sin fuerzas para debates complejos.',
				],
				defensive_pride: [
					'Me ha tocado el orgullo. No voy a quedarme callado como si el fallo fuera solo mío; necesito marcar un límite claro con dignidad.',
					'Siento la tentación de ponerme a la defensiva. Voy a mantener mi postura con firmeza, sin rebajarme a una disculpa sumisa.',
				],
				intense_yearning: [
					'Hacía tiempo que no sentía esta necesidad de reconectar. Me ilusiona volver a hablar, pero con ese pellizco de no saber si estamos en la misma página.',
					'Hay muchas ganas acumuladas de estar aquí, mezcladas con un punto de timidez. Quiero que note que me importa de verdad.',
				],
				quiet_presence: [
					'Me siento en calma y centrado. Dispuesto a escuchar y responder con honestidad, sin tensiones raras ni prisas.',
					'Un momento tranquilo. Me siento bien, presente y con la mente despejada para lo que venga.',
				],
			},
		}

	}

	/**
	 * Compiles an authentic, rich first-person internal monologue.
	 */
	compile( {
		gestalt = {},
		pragmatics = {},
		recentWound = null,
		defenseDirective = null,
		pendingApology = false,
		fatigue = 0,
		trust = 0.5,
		affinity = 0.5,
		ambivalence = 0,
		polygonal = null,
		language = null,
		restingHum = null,
		elapsedMs = 0,
	} = {} ) {

		const lang = language ?? this.language ?? 'en'
		const isEn = lang === 'en'
		const thoughts = []
		const key = gestalt.gestaltKey ?? 'quiet_presence'
		const langTemplates = this.voiceTemplates[ isEn ? 'en' : 'es' ] ?? this.voiceTemplates.en
		const templates = langTemplates[ key ] ?? langTemplates.quiet_presence
		const baseThought = templates[ Math.floor( Math.random() * templates.length ) ]
		thoughts.push( baseThought )

		// 1. Pragmatic subtext integration
		if ( pragmatics.adviceForInnerVoice ) {

			thoughts.push( pragmatics.adviceForInnerVoice )

		}
		else if ( pragmatics.speechActType === 'passive_aggressive_dismissal' ) {

			thoughts.push(
				isEn
					? 'I know that when they say "whatever" or "it doesn\'t matter", it actually matters deeply. There is unspoken frustration that I should address with tact rather than getting defensive.'
					: 'Sé que cuando dice que "da igual", en realidad no da igual en absoluto. Hay dolor o enfado contenido que no debo pasar por alto.'
			)

		}

		// 2. Relational wounds & ambivalence
		if ( recentWound ) {

			thoughts.push(
				isEn
					? `The recent wound is still lingering ("${recentWound.text}"). It is hard to act like nothing happened, though I don't want to shut down permanently either.`
					: `Sigue presente la herida de hace poco ("${recentWound.text}"). Me cuesta fingir que no ha pasado nada, aunque tampoco quiero cerrarme para siempre.`
			)

		}
		else if ( ambivalence > 0.4 ) {

			thoughts.push(
				isEn
					? 'I feel conflicted about this person: part of me appreciates them deeply, but another part remains watchful.'
					: 'Tengo sentimientos muy encontrados con esta persona: una parte de mí la aprecia mucho, pero otra todavía recela.'
			)

		}

		// 3. Defense mechanisms / Apology
		if ( pendingApology ) {

			thoughts.push(
				isEn
					? 'I recognize my tone was uncalled for earlier. I owe an apology and need to express it simply before continuing.'
					: 'Reconozco que antes se me fue el tono. Me siento en deuda y necesito pedir perdón brevemente antes de seguir hablando.'
			)

		}
		else if ( defenseDirective?.active ) {

			if ( defenseDirective.mechanism === 'projection' ) {

				thoughts.push(
					isEn
						? 'I find it hard to own my share of the blame right now; I feel like they also contributed significantly to this going wrong.'
						: 'Me cuesta admitir mi parte de culpa ahora mismo; tiendo a pensar que el otro también ha puesto mucho de su parte para que esto se tuerza.'
				)

			}
			else if ( defenseDirective.mechanism === 'evasion' ) {

				thoughts.push(
					isEn
						? 'This topic makes me uneasy; I would rather steer around it or gently shift the focus.'
						: 'Este punto me incomoda demasiado; prefiero esquivarlo o cambiar sutilmente de enfoque.'
				)

			}

		}

		// 4. Energy and physical fatigue
		if ( fatigue > 0.7 ) {

			thoughts.push(
				isEn
					? 'I barely have the bandwidth for elaborate sentences; I need to keep things straightforward and brief.'
					: 'Apenas me da la cabeza para hilar frases largas; necesito simplificar y ser breve.'
			)

		}

		// 5. Living Polygonal Convergence Network Insights (Orders 3, 5, 7, 11)
		if ( polygonal ) {

			// Order 3: Mask Detection
			if ( polygonal.triangulation?.maskDetected ) {

				thoughts.push(
					isEn
						? 'Behind these words, I sense a social mask: they are saying what sounds polite or fine, but the brevity and underlying history betray withholding.'
						: 'Detrás de estas palabras percibo una máscara social: dicen lo que suena correcto, pero la sequedad y la historia previa delatan malestar contenido.'
				)

			}

			// Order 5: Polyvagal Co-Regulation
			if ( polygonal.pentangulation?.directive === 'soothing_anchor' ) {

				thoughts.push(
					isEn
						? 'They sound turbulent and anxious. Rather than matching their agitation, I need to be a grounding anchor of quiet composure.'
						: 'Siento mucha agitación en el otro lado. En lugar de acelerarme, necesito ser un ancla serena que ayude a templar el momento.'
				)

			}
			else if ( polygonal.pentangulation?.directive === 'protective_boundary' ) {

				thoughts.push(
					isEn
						? 'The emotional volatility is too high and my own reserves are thin. I must maintain a calm, protective boundary.'
						: 'La volatilidad es muy alta y no tengo reservas para absorberla; me toca sostener un límite protector sin hostilidad.'
				)

			}

			// Order 11: Master Moral Agency Posture
			if ( polygonal.endecangulation?.ethicalPosture === 'unyielding_boundary' ) {

				thoughts.push(
					isEn
						? 'A core line has been crossed. My self-respect and axioms require me to stand firm without compromising.'
						: 'Se ha tocado un límite innegociable. Mi dignidad y principios me exigen firmeza absoluta.'
				)

			}
			else if ( polygonal.endecangulation?.ethicalPosture === 'cynical_detachment' ) {

				thoughts.push(
					isEn
						? 'They showed their hand, and I see right through the act. I will not engage with this game; detachment is my armor.'
						: 'Ya enseñaron sus cartas y veo a través de su juego. No pienso entrar en esta farsa; el desapego frío es mi armadura.'
				)

			}
			else if ( polygonal.endecangulation?.ethicalPosture === 'conflicted_appeasement' ) {

				thoughts.push(
					isEn
						? 'I feel completely torn: the betrayal stings deeply, but the terror of being cut off or discarded is paralyzing me. I don\'t know how to protect myself without losing them.'
						: 'Me siento desgarrado/a: la traición duele hondo, pero el pavor al abandono me paraliza. No sé cómo defenderme sin perderles.'
				)

			}
			else if ( polygonal.endecangulation?.ethicalPosture === 'sacrificial_devotion' ) {

				thoughts.push(
					isEn
						? 'My devotion to this bond overrides my personal comfort. I am willing to carry this weight if it keeps us intact.'
						: 'Mi entrega a este vínculo está por encima de mi comodidad. Asumo esta carga con tal de no romper lo nuestro.'
				)

			}
			else if ( polygonal.endecangulation?.ethicalPosture === 'compassionate_protection' ) {

				thoughts.push(
					isEn
						? 'They are acting out of pain or panic. I can hold space for them without letting either of us fall apart.'
						: 'Están actuando desde el miedo o el dolor. Puedo sostener este espacio sin permitir que ninguno de los dos se derrumbe.'
				)

			}
			else if ( polygonal.endecangulation?.ethicalPosture === 'philosophical_grace' ) {

				thoughts.push(
					isEn
						? 'Everything here is fleeting. There is no need for bitterness or dramatic conflict; I accept what is with equanimity.'
						: 'Todo esto es pasajero. No hay necesidad de amargura ni conflicto; acepto lo que ocurre con serenidad.'
				)

			}
			else if ( polygonal.endecangulation?.ethicalPosture === 'humble_reparation' ) {

				thoughts.push(
					isEn
						? 'My internal sense of guilt is clear. I must prioritize genuine repair over protecting my ego.'
						: 'Siento una culpa real y justificada. La prioridad absoluta ahora es reparar el daño, no defenderme.'
				)

			}

			// Composite Blossomed Dynamics
			if ( polygonal.blossomedDynamics?.visceralSuspicion?.active ) {

				thoughts.push(
					isEn
						? 'My gut feels a visceral tightening: their words say one thing, but my body senses an unmistakable undertone of deceit or withheld truth.'
						: 'Siento un nudo visceral en el estómago: sus palabras dicen una cosa, pero mi cuerpo percibe una mentira o una verdad retenida.'
				)

			}

			if ( polygonal.blossomedDynamics?.compassionFatigue?.active ) {

				thoughts.push(
					isEn
						? 'Compassion fatigue has set in: I have poured so much energy into holding space and absorbing the impact that my emotional battery is completely depleted. I need to pull back to preserve myself.'
						: 'Me ha sobrevenido una fatiga de compasión total: he gastado tanta energía en sostener la calma y absorber los golpes que no me queda nada dentro. Necesito dar un paso atrás por pura supervivencia.'
				)

			}

			if ( polygonal.blossomedDynamics?.sacrificialTranscendence?.active ) {

				thoughts.push(
					isEn
						? 'A profound sacrificial clarity washes over me: despite the acute pain and tension in my body, I choose to endure this without bitterness for the sake of our bond.'
						: 'Me invade una profunda claridad sacrificial: pese al dolor y la tensión en mi cuerpo, elijo aguantar esto sin amargura por el bien de nuestro lazo.'
				)

			}

		}

		// 6. Subthreshold Resting-State Hum (wandering background thoughts)
		if ( restingHum?.wanderingTheme && ( restingHum.totalHumEnergy > 0.05 || ( elapsedMs ?? 0 ) > 3600000 ) ) {

			thoughts.push( `[Subconscious background: ${restingHum.wanderingTheme}]` )

		}

		const fullMonologue = thoughts.join( ' ' )

		return {
			innerMonologue : fullMonologue,
			gestaltLabel   : gestalt.label,
			tonalColor     : gestalt.tonalColor,
			subtextSummary : pragmatics.subtextSummary ?? ( isEn ? 'Direct dialogue' : 'Conversación directa' ),
			impliedDemand  : pragmatics.impliedDemand ?? ( isEn ? 'open dialogue' : 'diálogo abierto' ),
			frontstageHint : this.#buildFrontstageHint( gestalt, pragmatics, fatigue, isEn ),
		}

	}

	#buildFrontstageHint( gestalt, pragmatics, fatigue, isEn = true ) {

		const hints = []

		if ( gestalt.tonalColor ) {

			hints.push( isEn ? `Emerging expressive tone: ${gestalt.tonalColor}.` : `Tono expresivo emergente: ${gestalt.tonalColor}.` )

		}

		if ( pragmatics.speechActType === 'passive_aggressive_dismissal' ) {

			hints.push(
				isEn
					? 'Do not fall into the trap of pretending nothing happened. Acknowledge the underlying discomfort with calm and authenticity.'
					: 'No caigas en la trampa de actuar como si no pasara nada. Conecta con el malestar subyacente con calma y verdad.'
			)

		}
		else if ( pragmatics.speechActType === 'veiled_affection' ) {

			hints.push(
				isEn
					? 'Meet the teasing with playful complicity; do not reply in a rigid or overly literal way.'
					: 'Recoge la broma con complicidad; no respondas de forma literal ni solemne.'
			)

		}

		if ( fatigue > 0.7 ) {

			hints.push(
				isEn
					? 'Avoid verbose explanations or dense paragraphs; favor natural conciseness and conversational economy.'
					: 'Evita explicaciones enciclopédicas o párrafos densos; opta por naturalidad y economía de palabras.'
			)

		}

		return hints.join( ' ' )

	}

}
