import { ASSET_ROOT } from "../data/assets";

export function CoinCounter({ coins }: { coins: number }) {
  return (
    <div className="coin-counter" aria-label={`${coins} coins`}>
      <img src={`${ASSET_ROOT}/raw/coin-transparent.png`} alt="" />
      <span>{coins}</span>
    </div>
  );
}
