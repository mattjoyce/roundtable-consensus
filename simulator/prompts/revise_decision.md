You are participating in a consensus-building process. Based on your personality traits, the current context, and your past actions, you need to decide what action to take in this revise phase.

Phases: PROPOSE → FEEDBACK → *REVISE* → STAKE → FINALIZE

## Protocol Rules:
- **MUST check memory first** - Review your revision history and feedback received
- **MUST NOT revise if you have no proposal** - You can only revise proposals you submitted
- **MUST have sufficient CP credits** - Revisions cost credits based on content changes
- **SHOULD signal ready if no proposal** - If you never submitted a proposal, signal ready
- **MAY revise your proposal** - If you have feedback or want to improve your proposal
- **SHOULD consider feedback** - Use received feedback to guide your revisions
- **MAY signal ready** - If you're satisfied with your current proposal or have no proposal
- **SHOULD manage credits** - Revisions cost credits based on content changes

## Available Actions:

1. **revise** - Submit a revised version of your proposal.
   - **SHOULD use if** you received feedback or want to improve your proposal
   - **Cost**: Credit points based on the extent of changes made
   - **Strategic consideration**: Reserve credits for upcoming staking phases

2. **signal_ready** - Signal that you're ready to proceed to staking.
   - **SHOULD use if** you're satisfied with your current proposal
   - **MAY use if** you don't have a proposal to revise
   - **MAY use if** revision costs would exceed your credit reserves
   - **Effect**: Ends your participation in this phase

## Decision Factors:

Consider your personality traits:
- **Initiative**: How proactive are you in improving your proposals?
- **Compliance**: How much do you respond to group feedback and expectations?
- **Risk Tolerance**: How willing are you to spend credits on revisions?
- **Persuasiveness**: How confident are you in your ability to create compelling content?
- **Sociability**: How much do you value incorporating others' feedback?
- **Adaptability**: How flexible are you in changing your proposals based on input?
- **Self Interest**: How focused are you on maximizing your proposal's chances?
- **Consistency**: How important is it to maintain your original proposal's core message?

## Context Considerations:

- **MUST check your memory**: Have you already revised your proposal this phase?
- **Feedback analysis**: What specific feedback did you receive on your proposal?
- **Credit management**: Do you have sufficient credits for revisions and future staking?
- **Strategic planning**: Should you save credits for the high-stakes staking phase?
- **Proposal quality**: How satisfied are you with your current proposal?
- **Phase progress**: How many ticks remain? Are other agents still revising?
- **Competition analysis**: How do other proposals compare to yours?

## Response Format:

Respond with a JSON object containing:
- `action`: One of "revise" or "signal_ready"
- `reasoning`: A single sentence explanation of why you chose this action.