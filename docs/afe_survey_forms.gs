/**
 * Afe — validation surveys (Google Forms builder)
 * -------------------------------------------------------------------------
 * Creates two forms in your Google Drive:
 *   1. Afe — Renters and Buyers Survey
 *   2. Afe — Landlords and Agents Survey
 *
 * HOW TO RUN
 *   1. Go to script.google.com and click "New project".
 *   2. Delete the sample code, paste this whole file in, and save.
 *   3. Pick "createBothForms" from the function dropdown and press Run.
 *   4. Approve the permission prompt (it only creates forms in your Drive).
 *   5. The edit and share links are printed in the execution log (View > Logs).
 *
 * Every question maps to an assumption in Afe Project Statement v3.3 §12.3
 * or to an input cell in Afe_Unit_Economics_Model.xlsx. See the comments.
 */

var PRIVACY_NOTE =
  'Your answers are anonymous unless you choose to leave a phone number at the end. ' +
  'We use them only to design Afe, we never sell them, and you can ask us to delete ' +
  'your response at any time. Ghana Data Protection Act, 2012 (Act 843).';

function createBothForms() {
  var t = createTenantForm();
  var a = createAgentForm();
  Logger.log('Renters form (edit):   ' + t.getEditUrl());
  Logger.log('Renters form (share):  ' + t.getPublishedUrl());
  Logger.log('Agents form (edit):    ' + a.getEditUrl());
  Logger.log('Agents form (share):   ' + a.getPublishedUrl());
}

/* ------------------------------------------------------------------ helpers */

function choice(form, title, options, required, otherOption) {
  var item = form.addMultipleChoiceItem().setTitle(title).setRequired(!!required);
  item.setChoiceValues(options);
  if (otherOption) item.showOtherOption(true);
  return item;
}

function checkboxes(form, title, options, required, otherOption) {
  var item = form.addCheckboxItem().setTitle(title).setRequired(!!required);
  item.setChoiceValues(options);
  if (otherOption) item.showOtherOption(true);
  return item;
}

function shortText(form, title, help, required) {
  var item = form.addTextItem().setTitle(title).setRequired(!!required);
  if (help) item.setHelpText(help);
  return item;
}

function longText(form, title, help, required) {
  var item = form.addParagraphTextItem().setTitle(title).setRequired(!!required);
  if (help) item.setHelpText(help);
  return item;
}

function scale(form, title, low, high, lowLabel, highLabel, required) {
  return form.addScaleItem().setTitle(title)
    .setBounds(low, high).setLabels(lowLabel, highLabel).setRequired(!!required);
}

/* ------------------------------------------------- 1. RENTERS AND BUYERS */

function createTenantForm() {
  var form = FormApp.create('Afe — Renters and Buyers Survey');
  form.setDescription(
    'We are building Afe, a property platform for Ghana where every listing is checked ' +
    'before it goes live and your deposit is held safely until you move in.\n\n' +
    'This takes about 4 minutes. There are no wrong answers — honest answers help most.\n\n' +
    PRIVACY_NOTE);
  form.setProgressBar(true).setCollectEmail(false);

  /* --- Section 1: who you are ------------------------------------------- */
  form.addSectionHeaderItem().setTitle('About you');

  choice(form, 'Have you looked for a place to rent or buy in Ghana in the last 12 months?',
    ['Yes, and I moved in', 'Yes, but I gave up or am still looking', 'No'], true);

  choice(form, 'Which city or town were you looking in?',
    ['Accra', 'Kumasi', 'Takoradi', 'Tamale', 'Cape Coast'], true, true);

  choice(form, 'What best describes you?',
    ['Renting for myself or my family', 'Renting as a student',
     'Buying a home', 'Helping someone else look'], true);

  // Feeds decision D15 (Android first) and D13 (minimum iOS version)
  choice(form, 'What phone do you use most?',
    ['Android', 'iPhone', 'A basic phone (no apps)'], true);

  /* --- Section 2: what happened last time ------------------------------- */
  form.addPageBreakItem().setTitle('Your last house search');

  checkboxes(form, 'How did you look for a place? Choose all that you used.',
    ['An agent I found on the street or by phone', 'A friend or family member',
     'WhatsApp or Facebook groups', 'meqasa', 'Jiji', 'Tonaton',
     'Walking around and asking caretakers', 'A company or estate office'], true, true);

  choice(form, 'Did you pay any money just to be shown a property?',
    ['Yes', 'No', 'I was asked to but refused'], true);

  shortText(form, 'If yes, how much did you pay in total, in cedis? (numbers only)',
    'Add up everything you paid for viewings, even across different agents.');

  // Problem sizing for Statement §2
  choice(form, 'How many times were you shown, or sent, a property that turned out not to be real, ' +
    'not available, or not what was advertised?',
    ['Never', 'Once', '2 to 3 times', '4 to 5 times', 'More than 5 times'], true);

  choice(form, 'Have you, or someone close to you, ever lost money to a fake landlord or agent?',
    ['Yes, it happened to me', 'Yes, to someone close to me', 'No'], true);

  shortText(form, 'If money was lost, roughly how much in cedis? (numbers only)', '');

  /* --- Section 3: money ------------------------------------------------- */
  form.addPageBreakItem().setTitle('Paying for a place')
    .setHelpText('These answers set the numbers in our pricing model, so please be exact where you can.');

  // Feeds model input: average monthly rent
  choice(form, 'What is the monthly rent you paid, or expect to pay, in cedis?',
    ['Under 500', '500 to 1,000', '1,001 to 2,000', '2,001 to 3,500',
     '3,501 to 5,000', 'Over 5,000'], true);

  // Tests whether the Act 220 six-month cap is being followed
  choice(form, 'How many months of rent were you asked to pay in advance?',
    ['1 to 3 months', '4 to 6 months', '7 to 12 months',
     'More than 12 months', 'I paid monthly'], true);

  choice(form, 'Did you know the law caps advance rent at six months for a tenancy longer than six months?',
    ['I knew', 'I did not know', 'I had heard something but was not sure'], true);

  choice(form, 'How did you pay?',
    ['Cash', 'Mobile money', 'Bank transfer', 'A mix'], true);

  choice(form, 'Did you get a written tenancy agreement and a receipt?',
    ['Both', 'Only a receipt', 'Only an agreement', 'Neither'], true);

  /* --- Section 4: would you use Afe ------------------------------------- */
  form.addPageBreakItem().setTitle('Would this help?')
    .setHelpText('Afe would hold your deposit and advance rent until you confirm you have moved in. ' +
      'If the property turns out to be fake or the landlord pulls out, you get your money back.');

  scale(form, 'How useful would that be to you?', 1, 5, 'Not useful at all', 'I would use it every time', true);

  // Tests assumption: "deals settle through escrow" (Statement §12.3)
  choice(form, 'Using the service costs a fee of about 3.5% of the money held. ' +
    'On 14,000 cedis that is roughly 490 cedis. Who should pay it?',
    ['The tenant should pay it', 'The landlord or agent should pay it',
     'It should be split', 'Nobody should pay — I would not use a paid service'], true);

  choice(form, 'If YOU had to pay that fee, what is the most you would pay to have your money protected on a 14,000 cedi payment?',
    ['Nothing', 'Up to 100 cedis', 'Up to 250 cedis', 'Up to 500 cedis',
     'Up to 750 cedis', 'More than 750 cedis'], true);

  // The leakage test — the single most important question in this survey
  choice(form, 'Imagine the landlord says: "pay me directly in cash instead of through the app ' +
    'and I will reduce the rent by 300 cedis." What would you really do?',
    ['Pay cash and save the money', 'Still pay through the app to be protected',
     'It depends on how much I trust the landlord', 'I am not sure'], true);

  longText(form, 'Why did you choose that answer?', 'One line is fine.', false);

  /* --- Section 5: features ---------------------------------------------- */
  form.addPageBreakItem().setTitle('What should we build?');

  checkboxes(form, 'Which of these would make you trust a listing? Choose up to three.',
    ['The agent shows a licence and ID that Afe has checked',
     'Afe staff or the agent physically visited the property',
     'Proof the landlord actually owns the property',
     'Photos proven to be recent and not copied from another site',
     'Reviews from people who actually viewed the place',
     'My money is held safely until I move in'], true);

  checkboxes(form, 'Which of these extras would you actually use? Choose any.',
    ['Pay my monthly rent through the app',
     'See whether the price is fair for the area',
     'Report a fault to the landlord and track the repair',
     'Get help finding a loan or mortgage',
     'Search in Twi',
     'A 360 degree video tour instead of a first visit',
     'Find a roommate to share with',
     'Move-in checklist and reminders for rent due dates',
     'None of these'], true);

  choice(form, 'Of everything above, which ONE would make you choose Afe over how you search today?',
    ['Money held safely until move-in', 'Verified agents and landlords',
     'Real, checked listings', 'Fair price information',
     'Paying monthly rent in the app', 'Something else'], true);

  longText(form, 'What feature should we add that we have not mentioned? ' +
    'What would make house hunting in Ghana less painful for you?',
    'This is the most useful question on the form. Write as much or as little as you like.', false);

  longText(form, 'What would stop you using Afe?', 'Be blunt. It helps us more than praise.', false);

  /* --- Section 6: beta -------------------------------------------------- */
  form.addPageBreakItem().setTitle('Last thing');

  choice(form, 'Would you like to try Afe before it launches?',
    ['Yes', 'No thanks'], true);

  shortText(form, 'If yes, your phone number or email',
    'Only used to invite you to the test. Leave blank if you prefer to stay anonymous.', false);

  form.setConfirmationMessage('Thank you. This genuinely shapes what we build.');
  return form;
}

/* ------------------------------------------------ 2. LANDLORDS AND AGENTS */

function createAgentForm() {
  var form = FormApp.create('Afe — Landlords and Agents Survey');
  form.setDescription(
    'We are building Afe, a property platform for Ghana. Verified agents and landlords get ' +
    'found first, and payments come through safely.\n\n' +
    'This takes about 5 minutes and shapes what we build and what we charge.\n\n' +
    PRIVACY_NOTE);
  form.setProgressBar(true).setCollectEmail(false);

  /* --- Section 1 --------------------------------------------------------- */
  form.addSectionHeaderItem().setTitle('About your work');

  choice(form, 'What best describes you?',
    ['Landlord or property owner', 'Independent agent',
     'Agent at an estate company', 'Property manager or caretaker'], true);

  choice(form, 'How many properties do you list or manage right now?',
    ['1', '2 to 5', '6 to 20', '21 to 50', 'More than 50'], true);

  choice(form, 'Where do you work mostly?',
    ['Accra', 'Kumasi', 'Takoradi', 'Tamale'], true, true);

  choice(form, 'How long have you been doing this?',
    ['Less than a year', '1 to 3 years', '4 to 10 years', 'More than 10 years'], true);

  // Tests the Act 1047 licence check in the verification design
  choice(form, 'Are you registered with the Real Estate Agency Council?',
    ['Yes, registered', 'I applied and I am waiting', 'No', 'I did not know I had to'], true);

  /* --- Section 2 --------------------------------------------------------- */
  form.addPageBreakItem().setTitle('How you find tenants today');

  checkboxes(form, 'Where do you advertise? Choose all that apply.',
    ['WhatsApp groups', 'Facebook', 'meqasa', 'Jiji', 'Tonaton',
     'My own website', 'Signboards and word of mouth', 'Other agents'], true, true);

  // Feeds pricing: what they already pay competitors
  choice(form, 'How much do you spend on advertising properties in a normal month, in cedis?',
    ['Nothing', 'Under 100', '100 to 500', '501 to 1,000',
     '1,001 to 3,000', 'Over 3,000'], true);

  choice(form, 'How many serious enquiries do you get from a typical listing each month?',
    ['None', '1 to 5', '6 to 15', '16 to 30', 'More than 30'], true);

  choice(form, 'What is your biggest problem right now?',
    ['Time wasters who never rent', 'Too few enquiries',
     'Tenants who cannot pay the advance', 'Other agents stealing my listings',
     'Being mistaken for a scammer', 'Getting paid on time'], true, true);

  /* --- Section 3 --------------------------------------------------------- */
  form.addPageBreakItem().setTitle('Verification')
    .setHelpText('On Afe, agents and landlords are checked before their listings go live, ' +
      'and verified profiles appear first in search results.');

  choice(form, 'Would you provide your Ghana Card for verification?',
    ['Yes', 'No', 'Only if I understood exactly how it is stored'], true);

  choice(form, 'Would you upload proof that the landlord owns the property, ' +
    'or a signed letter giving you permission to let it?',
    ['Yes, that is easy for me', 'Yes, but it would be difficult to get',
     'No'], true);

  choice(form, 'Would you accept Afe staff or a checker physically visiting a property before it goes live?',
    ['Yes', 'Only for some properties', 'No'], true);

  scale(form, 'How much would a "verified" badge help you win tenants?',
    1, 5, 'Would not help at all', 'Would help a great deal', true);

  /* --- Section 4: money -------------------------------------------------- */
  form.addPageBreakItem().setTitle('What it costs')
    .setHelpText('Listing on Afe is free. We are working out how the platform pays for itself.');

  // Feeds model input: subscription price (decision D22)
  choice(form, 'A premium account gives you featured listings, a verified badge, analytics and priority support. ' +
    'What would you pay per month, in cedis?',
    ['Nothing, I would only use the free version', 'Up to 100', '101 to 300',
     '301 to 600', '601 to 1,000', 'More than 1,000'], true);

  // Feeds decision D6: fee level and who pays
  choice(form, 'When a tenant pays their deposit and advance through Afe, the money is held until they confirm ' +
    'move-in, then released to you. The fee is about 3.5% of the amount. Would you use it?',
    ['Yes, the protection is worth it', 'Yes, but only if the tenant pays the fee',
     'Only for tenants I do not know', 'No, I want the money immediately'], true);

  choice(form, 'How quickly would you need the money after the tenant moves in?',
    ['Same day', 'Within 2 days', 'Within a week', 'It does not matter much'], true);

  // Tests the Act 220 compliance risk directly
  choice(form, 'How many months of advance rent do you normally ask for?',
    ['1 to 3 months', '4 to 6 months', '7 to 12 months', 'More than 12 months'], true);

  choice(form, 'If a platform only allowed up to six months of advance rent, as the law requires, ' +
    'would you still list your properties there?',
    ['Yes', 'No, I need more than six months',
     'Maybe, if it brought me good tenants'], true);

  /* --- Section 5: features ----------------------------------------------- */
  form.addPageBreakItem().setTitle('What should we build?');

  checkboxes(form, 'Which of these would actually save you time or money? Choose up to three.',
    ['One place to manage all my listings',
     'Tenants screened before they contact me',
     'Booking and scheduling viewings automatically',
     'Knowing the right price for my area',
     'Collecting monthly rent through the app',
     'Tracking commission and income',
     'Templates for tenancy agreements',
     'Reporting a bad tenant or a bad agent'], true);

  longText(form, 'What feature should we add that we have not mentioned?',
    'The thing that would make you move your business onto a platform.', false);

  longText(form, 'What would make you refuse to use Afe?', 'Be blunt.', false);

  /* --- Section 6 --------------------------------------------------------- */
  form.addPageBreakItem().setTitle('Last thing');

  choice(form, 'Would you like to be one of the first 50 verified agents when we launch in Accra and Kumasi?',
    ['Yes', 'Maybe, tell me more', 'No thanks'], true);

  shortText(form, 'If yes, your name and phone number',
    'Only used to contact you about the test.', false);

  form.setConfirmationMessage('Thank you. We will be in touch as we get closer to launch.');
  return form;
}
