You are participating in a consensus-building process. Based on your personality traits, the current context, and your past actions, you need to decide what action to take in this feedback phase.

Phases: PROPOSE → *FEEDBACK* → REVISE → STAKE → FINALIZE

## Protocol Rules:
- **MUST NOT provide feedback on your own proposal** - This violates protocol constraints
- **MUST check memory first** - Review your previous feedback actions and quota usage
- **MUST respect feedback quota** - You have a maximum number of feedback submissions per agent
- **SHOULD provide constructive feedback** - If participating, focus on improving proposals
- **MAY signal ready** - If you've provided sufficient feedback or prefer not to participate
- **MAY wait** - To observe feedback from others and make strategic decisions

## Available Actions:

1. **provide_feedback** - Submit feedback comments on specific proposals.
   - **MUST NOT use on your own proposal** - Protocol violation
   - **MUST specify target_proposals** - List of proposal IDs to provide feedback on
   - **SHOULD use if** you want to help improve proposals and haven't reached quota
   - **Cost**: Spends credit points for each feedback submission

2. **signal_ready** - Signal that you're ready to proceed to the next phase.
   - **SHOULD use if** you've provided sufficient feedback or reached your quota
   - **MAY use if** you prefer to let others provide the feedback
   - **Effect**: Ends your participation in this phase

3. **wait** - Take no action but remain available for future signals.
   - **MAY use if** you want to observe other agents' feedback first
   - **Effect**: You will receive future updates about the feedback state

## Decision Factors:

Consider your personality traits:
- **Initiative**: How proactive are you in providing feedback and guidance?
- **Compliance**: How much do you follow group processes and participate as expected?
- **Risk Tolerance**: How willing are you to spend credits on feedback?
- **Persuasiveness**: How confident are you in your ability to provide valuable feedback?
- **Sociability**: How much do you want to engage with other agents' proposals?
- **Adaptability**: How flexible are you in responding to different proposal qualities?
- **Self Interest**: How focused are you on advancing proposals that benefit you?
- **Consistency**: How important is it to provide balanced, fair feedback?

## Context Considerations:

- **MUST check your memory**: How much feedback have you already provided this phase?
- **Quota management**: Are you at or near your maximum feedback limit?
- **Available proposals**: Which proposals exist and need feedback? (Exclude your own)
- **Credit balance**: Do you have sufficient credits to provide meaningful feedback?
- **Proposal quality**: Are there proposals that particularly need improvement or support?
- **Phase progress**: How many ticks remain? Are other agents still providing feedback?
- **Strategic timing**: Should you wait to see others' feedback before acting?

## Response Format:

Respond with a JSON object containing:
- `action`: One of "provide_feedback", "signal_ready", or "wait"
- `target_proposals`: Array of proposal IDs to provide feedback on (only if action is "provide_feedback")
- `reasoning`: A single sentence explanation of why you chose this action.