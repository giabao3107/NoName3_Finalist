# How Big Can This Shop Become?

## Shop Growth Potential

---

## Context

In the development of the sales network, shops/merchants contribute at different levels in terms of contracts, funded volume, and business quality.

However, current sales performance does not necessarily reflect the true growth potential of a shop.

Two shops may generate the same level of sales today but have very different growth prospects:

- One may be significantly below its potential and have substantial room for growth.
- The other may already be close to the practical limit given its market, merchant profile, staffing, operating conditions, or other constraints.

Sales Management therefore needs to understand how far each shop can realistically grow, what is limiting its growth, and where additional resources should be allocated.

---

## Business Operation

The sales network includes different shop channels, including physical shops and online shops.

For physical shops, business can be generated through two different mechanisms:

- **Direct business at the physical shop** — Customers complete their transactions directly through the physical shop.
- **Cross-sell from physical shops to online business**

A physical shop may introduce or generate a lead for a customer, while the final contract is subsequently completed through an online shop/channel.

Therefore, the shop where the contract is ultimately booked may not always be the same shop that originally generated the customer opportunity.

The available data includes information from both Contract and Lead tables, which can be used to understand these relationships.

A **lead** is a potential sales opportunity generated from an existing customer contract, where the company identifies an opportunity to offer the customer an additional contract, product, or service.

The lead is assigned to the sales team to follow up with the customer, present the offer, and explore the possibility of closing a new contract.

A lead is mapped to a contract based on the following criteria:

- **SKP Client:** The lead and contract must belong to the same SKP client.
- **Product:** The product associated with the lead must match the product applied for in the contract.
- **Assignment Time:** The lead assignment timestamp must be earlier than or equal to the contract application timestamp.

---

## Business Challenge

You are asked to assess the growth potential of shops across the sales network.

The objective is not simply to identify the shops with the highest current sales, but to answer:

> "How far can a specific shop realistically grow, what constrains its growth, and what should Sales Management do to close the opportunity gap?"

Your analysis should clearly distinguish between:

- **Current Actual** — what the shop is achieving today.
- **Business-as-Usual** — what the shop is expected to achieve if current conditions and trends continue.
- **Attainable Potential** — what the shop could realistically achieve with feasible interventions.
- **Addressable Market Ceiling** — the potential market size that could theoretically be served within the defined scope and assumptions.

These concepts should not be used interchangeably.

Ultimately, Sales Management needs to understand which shops should receive additional resources, how much opportunity they represent, and why.

---

## Task

Using the available data, build a BI solution to assess and explain shop growth potential.

Your solution should help Management answer:

> "If two shops have similar current sales, how can we determine whether one has significant room to grow while the other does not?"

You are free to choose your own analytical approach and methodology.

Your analysis should consider, where relevant:

- What data and KPIs are needed to understand shop performance and potential.
- How current performance and future trajectory should be assessed.
- How realistic growth potential should be estimated.
- What factors create or constrain the opportunity gap.
- Whether the opportunity is driven by demand, execution, staffing, merchant characteristics, product mix, risk, or other factors.
- How shops should be prioritized when sales resources are limited.
- How the reliability and uncertainty of your estimates should be assessed.
- How your recommendations could be validated in practice.

**Analytics Tools and Methods:** No specific analytical methodology is required; however, it should clear what tools and analytical techniques are used, how they support each stage of the analysis, and why they are appropriate for the selected approach.

A simple and transparent approach with strong business logic, evidence, and validation may be more valuable than a complex model that is difficult to explain or apply.

---

## External Data

External data may be used if it helps improve the assessment of market potential or explain differences between shops.

Potential sources include official statistics from Vietnam's National Statistics Office, Google traffic patterns, population and income data, retail market indicators, geographic information, and other credible sources.

To receive strong evaluation, for any external dataset used, participants should clearly identify:

- Data source and reporting period.
- Geographic coverage and level of granularity.
- Method used to map or integrate the data with internal shop information.
- Business relevance and additional insights provided.
- Key assumptions, limitations, and potential biases.

External data is not mandatory. The quality and relevance of the evidence matter more than the number of external sources used.

---

# Submission Guidelines

## Requirement

Round 3 is a continuation of Round 2. Participants must present one coherent storyline, from understanding customers to evaluating the shop's growth potential.

Teams are not required to use the results or scores from Round 2 as inputs for Round 3.

All external data sources used in the submission must be clearly cited.

Team members are responsible for ensuring the accuracy, originality, and integrity of their submissions.

## Deadline

We will only recognize the latest valid submission received before the deadline.

After **16:00 on 22/10/2026 (GMT+7)**, the submission form will be closed, and no additional or replacement submissions will be accepted.

Submission platform/link: [ROUND 3 - PARALLAX](https://forms.gle/3ZgtNzQDFTaYzq69A)

---

## Submission Format

### A. Presentation Slides (Mandatory)

- Participants must submit 01 complete presentation deck, in which Round 2 content is briefly presented as the foundation for the Round 3 solution.
- There is no limit on the number of slides.
- Submit slides in English, using a 16:9 PDF format.
- The first slide must include the line "Visual supported by Canva".
- All external data sources must be clearly cited in the Appendix section at the end of the slide deck.
- The file name must be formatted as follows: `[TeamName_LeaderName_R03_BI10_Slide]`.

### B. Supporting Files (Mandatory)

Teams must submit supporting files that demonstrate their analysis process.

The supporting files must include:

- **Analysis Files:** All SQL scripts and Python files used to develop the solution.
- **README File:** For each external dataset, the README must clearly state the following five points:
  - Data source and reporting period.
  - Geographic coverage and level of granularity.
  - Method used to map or integrate the data with internal shop information.
  - Business relevance and additional insights provided.
  - Key assumptions, limitations, and potential biases.

All supporting files must be compressed into one ZIP file and named according to the following format: `[TeamName_LeaderName_R03_BI10_Attachments]`

---

## Final Presentation

Each team will have 10 minutes for presentation and 15 minutes for Q&A (including time for the Judges' questions and comments).

The Q&A session will follow this order:

1. The Judges ask all questions in a single round.
2. The team responds.
3. The Judges give their final comments.

The judging criteria will not be disclosed to participants.

---

## Notes!

All submitted files must be clearly named, accessible, and usable during the evaluation process.

The Team Leader is responsible for submitting the final submission and verifying all information and files before submission.

Each team is encouraged to record their screen throughout the submission process, including file uploads and confirmation of successful submission. The recording may serve as supporting evidence in case of system errors or technical issues.

---

## Contact Us

Don't hesitate to ask everything from us!

### ITB Club

- [ITB Club UEL Facebook](https://www.facebook.com/itbclub.uel)
- Email: businessintelligence.uel@gmail.com

### Head of Research Dept.

**Vòng Hữu Quân**
- Email: quanvhk24416@st.uel.edu.vn
- Phone: 0971793212

### Lead of Academic Team BI10

**Nguyễn Thị Kiều Tiên**
- Email: tienntkk24406h@st.uel.edu.vn
- Phone: 0935010927
