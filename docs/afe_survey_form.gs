/**
 * Afe — market validation survey
 * Builds the whole Google Form, with branching by respondent type.
 *
 * HOW TO USE
 *  1. Go to script.google.com, New project, delete the sample code.
 *  2. Paste this file in, Save.
 *  3. Select createAfeSurvey in the function dropdown, Run, and allow access.
 *  4. The form URL is printed in the execution log (View > Logs).
 *  5. In the form: Responses tab > link to a Google Sheet.
 *
 * Every question maps to an assumption in Project Statement Section 12.3.
 */

function createAfeSurvey() {
  var form = FormApp.create('Afe — how people rent in Ghana');

  form.setDescription(
    'We are building a service that checks properties and agents before a listing goes live, ' +
    'and holds deposits safely until you confirm you have moved in.\n\n' +
    'This survey takes about 5 minutes. There are no right answers — we want the truth about how renting ' +
    'actually works.\n\n' +
    'Your answers are anonymous. We do not ask for your name, your Ghana Card number, or your address. ' +
    'Contact details at the end are optional, and used only to invite you to the test version. ' +
    'You can stop at any time.'
  );

  form.setProgressBar(true);
  form.setCollectEmail(false);          // anonymous: people answer money questions more honestly
  form.setAllowResponseEdits(false);
  form.setLimitOneResponsePerUser(false); // sign-in would exclude people without Google accounts
  form.setShuffleQuestions(false);
  form.setConfirmationMessage(
    'Thank you. If you left your number, we will contact you when the test version opens in Accra and Kumasi.'
  );

  // ---------------------------------------------------------------- sections
  var tenantPage   = form.addPageBreakItem().setTitle('Finding and paying for a place')
                         .setHelpText('About the last place you rented or tried to rent.');

  buildTenant(form);

  var landlordPage = form.addPageBreakItem().setTitle('Letting your property')
                         .setHelpText('About how you let the places you own.');
  buildLandlord(form);

  var agentPage    = form.addPageBreakItem().setTitle('Working as an agent')
                         .setHelpText('About your listings, clients and fees.');
  buildAgent(form);

  var contactPage  = form.addPageBreakItem().setTitle('Optional: stay in touch');
  buildContact(form);

  // after each branch, jump straight to the contact page
  tenantPage.setGoToPage(contactPage);
  landlordPage.setGoToPage(contactPage);
  agentPage.setGoToPage(contactPage);

  // ---------------------------------------------------------------- screening question (must sit first)
  var screen = form.addMultipleChoiceItem()
    .setTitle('Which of these describes you best?')
    .setHelpText('Pick the one you spend the most time doing. Different questions follow for each.')
    .setRequired(true);

  screen.setChoices([
    screen.createChoice('I rent, or I am looking for a place to rent', tenantPage),
    screen.createChoice('I own property that I rent out', landlordPage),
    screen.createChoice('I work as an agent or caretaker', agentPage)
  ]);

  var city = form.addMultipleChoiceItem()
    .setTitle('Where are you?')
    .setChoiceValues(['Accra', 'Kumasi', 'Takoradi', 'Tamale', 'Somewhere else in Ghana', 'Outside Ghana'])
    .setRequired(true);

  // move the two screening items to the top, above the first page break
  form.moveItem(screen.getIndex(), 0);
  form.moveItem(city.getIndex(), 1);

  Logger.log('EDIT: ' + form.getEditUrl());
  Logger.log('SHARE: ' + form.getPublishedUrl());
}

/* ============================================================ TENANTS */
function buildTenant(form) {
  form.addCheckboxItem()
    .setTitle('How did you look for your last place?')
    .setHelpText('Tick everything you used.')
    .setChoiceValues([
      'An agent or caretaker I met in person',
      'WhatsApp groups',
      'Facebook or Instagram',
      'Jiji, Tonaton or a similar site',
      'meqasa or another property site',
      'Friends and family',
      'Walking around looking for "To Let" signs'
    ])
    .showOtherOption(true)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('In the last two years, did you pay a fee just to be shown a place?')
    .setHelpText('Sometimes called an inspection fee or viewing fee.')
    .setChoiceValues(['Yes, more than once', 'Yes, once', 'No', 'I was asked but refused'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('If you paid viewing fees, how much in total?')
    .setChoiceValues(['I did not pay any', 'Under GHS 100', 'GHS 100–300', 'GHS 300–600', 'More than GHS 600'])
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('Have you ever lost money to a fake listing, a fake agent, or a place that was already taken?')
    .setChoiceValues(['Yes', 'No', 'It happened to someone close to me'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('If yes, roughly how much did you lose?')
    .setChoiceValues(['Nothing', 'Under GHS 500', 'GHS 500–2,000', 'GHS 2,000–10,000', 'More than GHS 10,000'])
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('How many months of rent were you asked to pay in advance, the last time?')
    .setHelpText('The law allows a maximum of six months for a tenancy longer than six months.')
    .setChoiceValues(['1–2 months', '3–6 months', '1 year', '2 years', 'More than 2 years', 'I cannot remember'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('What is your monthly rent, or the rent you are looking for?')
    .setChoiceValues([
      'Under GHS 500', 'GHS 500–1,000', 'GHS 1,000–2,000',
      'GHS 2,000–4,000', 'GHS 4,000–8,000', 'Over GHS 8,000'
    ])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How did you pay?')
    .setChoiceValues([
      'Cash in hand', 'Mobile money to a person', 'Mobile money to a business',
      'Bank transfer', 'Cheque'
    ])
    .showOtherOption(true)
    .setRequired(true);

  form.addScaleItem()
    .setTitle('Imagine your deposit and advance rent are held safely, and only released to the landlord after you confirm you have moved in. How useful would that be to you?')
    .setBounds(1, 5)
    .setLabels('Not useful at all', 'I would insist on it')
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Holding the money safely costs about 3.5% of the amount. Who do you think should pay that?')
    .setHelpText('On GHS 14,000 held, that is about GHS 490.')
    .setChoiceValues([
      'The tenant', 'The landlord or agent', 'Split between both',
      'Nobody — I would not use it if there is a fee'
    ])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('If the fee were GHS 490 on a GHS 14,000 payment, would you still use it?')
    .setChoiceValues(['Yes', 'Maybe, if the landlord agreed', 'No, too expensive', 'No, I would rather pay cash directly'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('What kind of phone do you use?')
    .setChoiceValues(['Android', 'iPhone', 'A basic phone, no apps'])
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('What is the worst part of looking for a place here?')
    .setRequired(false);
}

/* ============================================================ LANDLORDS */
function buildLandlord(form) {
  form.addMultipleChoiceItem()
    .setTitle('How many places do you rent out?')
    .setChoiceValues(['1', '2–3', '4–10', '11–30', 'More than 30'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Who finds your tenants?')
    .setChoiceValues(['I do it myself', 'An agent', 'A caretaker', 'Family or friends', 'It varies'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('If you use an agent, what do they charge?')
    .setChoiceValues(['No agent', 'Less than one month of rent', 'One month of rent', 'Two months or more', 'A percentage of the rent'])
    .setRequired(false);

  form.addMultipleChoiceItem()
    .setTitle('How many months of rent do you ask for in advance?')
    .setChoiceValues(['1–2 months', '3–6 months', '1 year', '2 years', 'It depends on the tenant'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('The law caps advance rent at six months. Would you let a place on those terms?')
    .setChoiceValues([
      'Yes, that is what I already do',
      'Yes, if the payment were guaranteed',
      'Only at a higher monthly rent',
      'No'
    ])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('What gives you the most trouble as a landlord?')
    .setChoiceValues([
      'Tenants who do not pay',
      'Agents who collect money and disappear',
      'Long empty periods between tenants',
      'Damage to the property',
      'Time wasted showing the place',
      'Getting tenants out'
    ])
    .showOtherOption(true)
    .setRequired(true);

  form.addScaleItem()
    .setTitle('Would you accept your money being released a day or two after the tenant confirms they have moved in, in exchange for the tenant being verified?')
    .setBounds(1, 5)
    .setLabels('Never', 'Happily')
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('To list on a service like this, you would upload your ID and proof that the property is yours. How do you feel about that?')
    .setChoiceValues([
      'Fine, I have the documents',
      'Fine, but I do not have formal documents',
      'Uncomfortable, but I would do it',
      'I would not do it'
    ])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How long does a place usually stay empty between tenants?')
    .setChoiceValues(['Under 2 weeks', '2–4 weeks', '1–3 months', 'More than 3 months'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Would you pay to have your listing verified and shown first?')
    .setChoiceValues(['Yes', 'Only if it filled the place faster', 'No, the tenant or agent should pay', 'No'])
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('What would make you trust a service like this with your property?')
    .setRequired(false);
}

/* ============================================================ AGENTS */
function buildAgent(form) {
  form.addMultipleChoiceItem()
    .setTitle('Are you licensed with the Real Estate Agency Council?')
    .setHelpText('The Real Estate Agency Act, 2020 requires it. We ask because we plan to check licences.')
    .setChoiceValues(['Yes', 'No', 'I applied and I am waiting', 'I have never heard of it'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How many places do you have on your books right now?')
    .setChoiceValues(['1–5', '6–15', '16–40', 'More than 40'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('How many deals do you close in a normal month?')
    .setChoiceValues(['Less than 1', '1–2', '3–5', '6–10', 'More than 10'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('What do you charge the tenant when a deal closes?')
    .setChoiceValues(['Nothing', 'Less than one month of rent', 'One month of rent', 'Two months of rent', 'A percentage'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('Do you charge for viewings?')
    .setChoiceValues(['Yes, always', 'Sometimes', 'No'])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('Where do you advertise?')
    .setChoiceValues(['WhatsApp', 'Facebook or Instagram', 'Jiji or Tonaton', 'meqasa', 'TikTok', 'Signs on the property', 'Word of mouth'])
    .showOtherOption(true)
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('What do you pay each month to advertise, across all of them?')
    .setChoiceValues(['Nothing', 'Under GHS 100', 'GHS 100–300', 'GHS 300–600', 'GHS 600–1,000', 'More than GHS 1,000'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('What would you pay each month for verified listings, a verified badge and leads?')
    .setChoiceValues(['Nothing', 'Up to GHS 100', 'GHS 100–300', 'GHS 300–600', 'GHS 600–1,000', 'More than GHS 1,000'])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('If the tenant paid through the platform, and the money reached you a day or two after they moved in, minus 3.5%, what would you do?')
    .setHelpText('This is the question we most need an honest answer to.')
    .setChoiceValues([
      'Use it — safer for everyone',
      'Use it only for tenants I do not know',
      'Take cash outside the platform instead',
      'Depends on who pays the 3.5%'
    ])
    .setRequired(true);

  form.addMultipleChoiceItem()
    .setTitle('You would upload your ID, your licence and proof that you may let each property. How do you feel about that?')
    .setChoiceValues(['Fine', 'Fine for my own listings, hard for ones I get from other agents', 'Too much work', 'I would not do it'])
    .setRequired(true);

  form.addScaleItem()
    .setTitle('How often do you lose a client because they do not trust you have a real property?')
    .setBounds(1, 5)
    .setLabels('Never', 'All the time')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('What would make you move your deals onto a platform like this?')
    .setRequired(false);
}

/* ============================================================ CONTACT */
function buildContact(form) {
  form.addMultipleChoiceItem()
    .setTitle('Would you like to try the test version when it opens in Accra and Kumasi?')
    .setChoiceValues(['Yes', 'No thank you'])
    .setRequired(true);

  form.addTextItem()
    .setTitle('Phone number or email (optional)')
    .setHelpText('Only used to invite you to the test. We will not share it with anyone else.')
    .setRequired(false);
}
