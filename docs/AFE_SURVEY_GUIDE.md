# Afe validation survey — how to run it

Companion to `afe_survey_form.gs` and Section 12.3 of the Project Statement.

## Building the form

Google Forms cannot import questions from a document. Its own "Import questions" button only pulls
from another Form. The reliable route is the script:

1. Open **script.google.com** → New project → delete the sample code.
2. Paste in `afe_survey_form.gs` → Save.
3. Choose `createAfeSurvey` in the function dropdown → Run → allow access.
4. Open **View → Logs** for the edit and share links.

Re-running creates a second form, so run it once and edit in the Forms UI after that.

## Settings to turn on

| Setting | Value | Why |
|---|---|---|
| Progress bar | On | Three branches of different lengths; people need to see the end |
| Collect email addresses | **Off** | Advance rent above six months is illegal. Anonymity gets honest answers |
| Limit to 1 response | **Off** | It forces a Google sign-in, which excludes part of your sample |
| Response validation | On the phone/email field only | Heavy validation on a phone makes people abandon the form |
| Shuffle option order | On for the "where do you advertise" and "how did you look" lists | Reduces the bias toward the first option |
| Section branching | Already in the script | Question 1 sends each respondent to their own section |
| Quiz mode | Off | There are no right answers |
| Confirmation message | Already set | Tells people what happens next |
| Link to Sheets | Do it before sharing | Responses tab → the green Sheets icon |

## Distribution

- Shorten the link and make a QR code for field use. Agents and caretakers respond better to a QR on a card than to a link in a message.
- Post in the WhatsApp groups where listings already circulate. That is where your respondents are.
- For the agent section, aim for face-to-face. Agents rarely fill in forms from strangers, and the licensing question needs trust.
- Target sample: **150 tenants, 40 landlords, 40 agents**, all in Accra and Kumasi. Below about 30 per group, the percentages are not worth reading.
- Offer nothing for tenant responses. For agents, a place on the beta list works better than airtime.

## What each group tells you

| Section | Assumption it tests (Statement 12.3) | The answer that matters most |
|---|---|---|
| Tenants | Fee tolerance, escrow demand | The GHS 490 fee question. If most say "too expensive", the 3.5% rate is wrong |
| Tenants | Platform reach | Android vs iPhone split, which settles decision D15 |
| Landlords | Six-month cap acceptance | If most say "no" or "only at a higher rent", Ghana's legal cap is a growth ceiling you have to plan around |
| Agents | Leakage | "Take cash outside the platform instead". This single answer decides whether the transaction fee model works |
| Agents | Subscription pricing | What they pay now versus what they would pay, which sets decision D22 |
| Agents | Verification feasibility | The share who are licensed. If it is very low, licence checking cannot be a hard requirement at launch |

## Reading the results honestly

- People overstate willingness to pay in surveys. Treat the subscription figures as a ceiling, not a forecast, and discount them before they go into the model.
- Stated intent to use escrow means little until someone actually pays. The beta, not the survey, settles that.
- Watch for agents answering as they think you want. The cash-outside-the-platform option is phrased to make that answer socially acceptable — keep it that way.

## Data protection

Under the Data Protection Act, 2012 (Act 843):

- The form asks for no names, no Ghana Card numbers and no addresses. Keep it that way.
- Contact details are optional and used only for beta invitations. Say so, as the form already does.
- Keep the response sheet in a restricted Drive folder, not shared by link.
- Delete contact details once the beta list is built.
