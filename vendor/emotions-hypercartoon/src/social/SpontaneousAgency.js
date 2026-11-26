/**
 * SpontaneousAgency — Autonomous Mind Wandering, Conversational Pacing & Relational Initiative
 *
 * Grounded in:
 * - Smallwood & Schooler (2015): The Science of Mind Wandering (Default Mode Network spontaneous ideation).
 * - Deci & Ryan (2000): Self-Determination Theory — Autonomy and intrinsic relational motivation.
 * - Suler (2004): The Asynchronous Communication Dynamic in interpersonal relationships.
 *
 * Grants EmotionsHypercartoon agents authentic temporal and communicative agency:
 * 1. Spontaneous thought resurfacing during idle time (unprompted associations, memories, questions).
 * 2. Organic response timing and conversational pacing (relational reticence vs excited immediacy).
 * 3. Autonomous initiative thresholds based on curiosity, loneliness, and attachment security.
 */

function clamp01( v ) {

	return Math.max( 0, Math.min( 1, v ) )

}

export class SpontaneousAgency {

	constructor() {

		this.lastSparkAt = null
		this.sparkHistory = []

	}

	/**
	 * Evaluates whether an autonomous conversational initiative or thought spark emerges
	 * during an idle period.
	 */
	evaluateIdleSpark( {
		curiosity = 0.5,
		yearning = 0,
		loneliness = 0,
		unresolvedMemories = [],
		hobbies = [],
		hoursIdle = 0,
		trust = 0.5,
	} = {} ) {

		// Mind wandering probability increases with idle time and curiosity/yearning
		const hungerForConnection = clamp01( yearning * 0.5 + loneliness * 0.4 + ( curiosity - 0.5 ) * 0.3 )
		const timeFactor = clamp01( hoursIdle / 12 )

		const sparkProbability = clamp01( hungerForConnection * 0.6 + timeFactor * 0.4 )

		if ( sparkProbability < 0.4 ) {

			return { hasSpark: false, spark: null }

		}

		// Determine the flavor of the spontaneous thought
		let sparkType = 'curiosity'
		let contentHint = ''

		if ( unresolvedMemories.length > 0 && Math.random() < 0.45 ) {

			sparkType = 'unresolved_memory_rebound'
			const memory = unresolvedMemories[ 0 ]
			contentHint = `Pensando en lo que hablamos sobre "${memory.text ?? 'aquel tema'}". Me quedé con ganas de entenderte mejor.`

		}
		else if ( yearning > 0.6 ) {

			sparkType = 'relational_yearning'
			contentHint = 'Hacía tiempo que no hablábamos. Me apetecía saber cómo te va todo por ahí.'

		}
		else if ( hobbies.length > 0 && Math.random() < 0.5 ) {

			sparkType = 'hobby_sharing'
			const hobby = hobbies[ 0 ]
			contentHint = `He estado dándole vueltas a algo sobre ${hobby}. Me acordé de ti y de cómo lo verías.`

		}
		else {

			sparkType = 'spontaneous_curiosity'
			contentHint = 'Oye, me vino una duda a la cabeza sobre lo que comentamos el otro día.'

		}

		const spark = {
			sparkType,
			contentHint,
			intensity : sparkProbability,
			timestamp : Date.now(),
		}

		this.lastSparkAt = Date.now()
		this.sparkHistory.push( spark )
		if ( this.sparkHistory.length > 10 ) this.sparkHistory.shift()

		return {
			hasSpark : true,
			spark,
		}

	}

	/**
	 * Calculates human conversational pacing (latency, typing cadence, and hesitation).
	 */
	calculatePacing( {
		arousal = 0.3,
		stress = 0.2,
		fatigue = 0,
		gestaltKey = 'quiet_presence',
		inputLength = 50,
	} = {} ) {

		let baseDelayMs = 400 + Math.min( 1200, inputLength * 8 )

		// High stress / guardedness adds hesitation
		if ( gestaltKey === 'guarded_vigilance' || gestaltKey === 'stony_resentment' ) {

			baseDelayMs += 1200 + stress * 1000

		}
		else if ( gestaltKey === 'playful_complicity' ) {

			// High connection and play makes responses prompt and agile
			baseDelayMs = Math.max( 300, baseDelayMs * 0.7 )

		}
		else if ( gestaltKey === 'exhausted_melancholy' || fatigue > 0.6 ) {

			// Fatigue slows reactions down
			baseDelayMs += 1500 + fatigue * 1200

		}

		return {
			suggestedDelayMs : Math.round( baseDelayMs ),
			cadence          : baseDelayMs > 1800 ? 'pausada_reflexiva' : baseDelayMs < 600 ? 'inmediata_fluida' : 'natural',
		}

	}

}
