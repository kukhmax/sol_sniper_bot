



















































































export type LiquiditySide = 'a' | 'b'
// for inner instruction
export type AmountSide = 'base' | 'quote'

/* ===================== pool keys =========================*/
export type LiquidityPoolKeysV4 = {
    [T in keyof ApiPoolInforItem]: string extends ApiPoolInforItem[T] ? PublicKey : ApiPoolInforItem[T]
}

/**
 * Full liquidity pool keys that bould transaction need
*/
export type LiquidityPoolKeys = LiquidityPoolKeysV4

export interface LiquidityAssociatedPoolkeysV4
    extends Omit<
        LiquidityPoolKeysV4,
        'marketBaseVault' | 'marketQuoteVault' | 'marketBids' | 'marketAsks' | 'marketEventQueue'
    > {
    nonce: number
}























export interface ApiPoolInfoV4 {
    id: string
    baseMint:string
    quoteMint:string
    lpMint:string
    baseDecimals: number
    quoteDecimals: number
    lpDecimals: number
    version: 4
    programId: string
    authority: string
    openOrders: string
    targetOrders: string
    quoteVault: string
    baseVault: string
    withdrawQueue: string
    lpVault: string
    marketVersion: 3
    marketProgramId: string
    marketId: string
    marketAuthority: string
    marketBaseVault: string
    marketQuoteVault: string
}