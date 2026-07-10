import type { ActionMeta, ActionName, Influence, Provider } from "../types/game";

export const ASSET_ROOT = "/assets";

export const influenceImages: Record<Influence, string> = {
  Duke: `${ASSET_ROOT}/raw/duke.png`,
  Assassin: `${ASSET_ROOT}/raw/assassin.png`,
  Captain: `${ASSET_ROOT}/raw/captain.png`,
  Ambassador: `${ASSET_ROOT}/raw/ambassador.png`,
  Contessa: `${ASSET_ROOT}/raw/contessa.png`
};

export const providerIcons: Partial<Record<Provider, string>> = {
  openai: `${ASSET_ROOT}/raw/openai-icon.png`,
  claude: `${ASSET_ROOT}/raw/claude-icon.jpg`,
  gemini: `${ASSET_ROOT}/raw/gemini-icon.jpeg`
};

export const providerColors: Record<Provider, string> = {
  human: "#efbd55",
  openai: "#62d3aa",
  claude: "#e68b5d",
  gemini: "#78b7ff",
  random: "#c7b5ff",
  empty: "#efbd55"
};

export const influenceDescriptions: Record<Influence, string> = {
  Duke: "Claims Tax and blocks Foreign Aid.",
  Assassin: "Claims Assassinate to remove an opponent's influence.",
  Captain: "Claims Steal and blocks Steal.",
  Ambassador: "Claims Exchange and blocks Steal.",
  Contessa: "Blocks Assassinate."
};

export const actions: Record<ActionName, ActionMeta> = {
  Income: {
    name: "Income",
    card: `${ASSET_ROOT}/raw/action-cards/income.png`,
    effect: "Take 1 coin.",
    cost: 0,
    target: false,
    blockable: false
  },
  "Foreign Aid": {
    name: "Foreign Aid",
    card: `${ASSET_ROOT}/raw/action-cards/foreign-aid.png`,
    effect: "Take 2 coins. Any opponent may block with Duke.",
    cost: 0,
    target: false,
    blockable: true
  },
  Tax: {
    name: "Tax",
    card: `${ASSET_ROOT}/raw/action-cards/tax.png`,
    effect: "Claim Duke and take 3 coins.",
    cost: 0,
    target: false,
    claim: "Duke",
    blockable: false
  },
  Steal: {
    name: "Steal",
    card: `${ASSET_ROOT}/raw/action-cards/steal.png`,
    effect: "Claim Captain and take 2 coins from a target.",
    cost: 0,
    target: true,
    claim: "Captain",
    blockable: true
  },
  Exchange: {
    name: "Exchange",
    card: `${ASSET_ROOT}/raw/action-cards/exchange.png`,
    effect: "Claim Ambassador and exchange cards with the court deck.",
    cost: 0,
    target: false,
    claim: "Ambassador",
    blockable: false
  },
  Assassinate: {
    name: "Assassinate",
    card: `${ASSET_ROOT}/raw/action-cards/assassinate.png`,
    effect: "Pay 3 coins and choose a target to lose influence.",
    cost: 3,
    target: true,
    claim: "Assassin",
    blockable: true
  },
  Coup: {
    name: "Coup",
    card: `${ASSET_ROOT}/raw/action-cards/coup.png`,
    effect: "Pay 7 coins and force a target to lose influence.",
    cost: 7,
    target: true,
    blockable: false
  }
};

export const actionOrder = Object.keys(actions) as ActionName[];

export const responseCards = {
  challenge: `${ASSET_ROOT}/raw/action-cards/challenge.png`,
  blockForeignAid: `${ASSET_ROOT}/raw/action-cards/block-foreign-aid.png`,
  blockSteal: `${ASSET_ROOT}/raw/action-cards/block-steal.png`,
  blockAssassin: `${ASSET_ROOT}/raw/action-cards/block-assassin.png`
};
