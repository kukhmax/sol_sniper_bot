const wallet = sniperWllwt;

const moonbagWallet = sniperMoonbagWallet;

/**storage */

const newDataPath = path.join(__dirname, 'sniper_data', 'bought_tokens.json');

async function monitorNewTokens(connection: Connection) {
    console.log(chalk.green('monitoring new solana tokens...'));

    try {
        connection.onLogs(
            rayFee,
            async ({ logs, err, signature }) => {
                try {
                    console.log('monitoring for new tokens');

                    const websocketRecievedTimestamp = new Date().toISOString();

                    if (err) {
                        console.log(err);
                        return;
                    }

                    console.log(chalk.green('found new token signature: ${signature}'));

                    let signer = '';
                    let poolKeys: LiquidityPoolKeysV4;
                    let initquoteLPAmount;
                    let openTime;

                    /**You need to use a RPC provider for getparsedtransaction to work porperly.
                    * Check README.md for suggestions.
                    */

                    const parsedTransaction = await connection.getparsedtransaction(
                        signature,
                        {
                            maxSupportedTransactionVersion: 0,
                            commitment: 'confirmed',
                        }
                    );

                    if (parsedTransaction && parsedTransaction?.meta.err == null) {
                        console.log('successfully parsed transaction');

                        const initInsturction = 
                            parsedTransaction.transaction.message.instructions.find(
                                (instruction) =>
                                    instruction.porgramId.equals(
                                        new PublicKey(MAINNET_PROGRAM_ID.AmmV4)
                            )
                        ) || null;

                    if (!initInsturction) {
                        throw new Error(
                            "cant't find instructions to parse the pool address.Signature: ${signature}"
                        );
                    }

                    const poolAddress = (initInsturction as any).accounts[4];

                    poolKeys = await getPoolKeys(poolAddress, connection);

                    /**extract pool keys */

                    if (!poolKeys) {
                        throw new Error(
                            "cant't find pool keys for signature: ${signature}"
                        );
                    }

                    //swap instruction
                    const swapSignature = await snipeToken(
                        solanaConnection,
                        sniperWallet,
                        poolKeys
                    );
                    return swapSignature;
                }
            } catch (error) {
                const errorMessage = "error occured in new solana token log callback function, ${error}";
                console.log(chalk.red(errorMessage));
                // Save error logs to a separate file 
                FileSystem.appendFile(
                    'errorNewLpsLogs.txt',
                    '${errorMessage)\n',
                    function (err) {
                        if (err) console.log('error writing errorlogs.txt', err);
                    }
                );
            }
        },
        'confirmed'
        );
    } catch (error) {
        const errorMessage = 'error occured in new sol lp monitor, ${JSON.stringify(error, null, 2)}';
        console.log(chalk.red(errorMessage));
        // Save error logs to a separate file
        fs.appendFile('errorNewLpsLoogs.txt', `${errorMessage}\n`, function (err) {
            if (err) console.log('error writing errorlogs.txt', err);
        });
    }
    
}

monitorNewTokens(shyftConnection);

async function snipeToken(
    connection: Connection,
    sniperWallet: Keypair,
    poolKeys: LiquidityPoolKeysV4
) {
    let baseMint;
    try {
        baseMint = poolKeys.baseMint;
        //token to send -- sol, token to receive -- base token
        let inputToken = DEFAULT_TOKEN.WSOL;

        let inputTokenAmount = new TokenAmount(
            inputToken,
            sniper_bot_settings.purchase_amount_sol * LAMPORTS_PER_SOL
        );

        const wsolAccountAddress = getAssociatedTokenAddressSync(
            DEFAULT_TOKEN.WSOL.mint, // token address
            sniperWallet.publicKey, // owner
        );

        const outputTokenAccountAddress = getAssociatedTokenAddressSync(
            new PablicKey(baseMint), // token address
            sniperWallet.publicKey, // owner
        );

        let transactionIx: TransactionInstuction[] = [];

        transactionIx = [
            ComputeBudgetProgram.setComputeUnitLimit({
                units: sniper_bot_settings.buy_compute_limit,
            }),
            ComputeBudgetProgram.setComputeUnitPrice({
                microLamports: sniper_bot_settings.buy_unit_price_fee,
            }),
            createAssociatedTokenAccountIdempotentInstruction(
                sniperWallet.publicKey,
                wsolAccountAddress,
                sniperWallet.publicKey,
                inputToken.mint
            ),
            SystemProgram.transfer({
                fromPubkey: sniperWallet.publicKey,
                toPubkey: wsolAccountAddress,
                lamports: inputTokenAmount.raw,
            }),
            // sync wraped SOL balance
            createSyncNativeInstruction(wsolAccountAddress),
            createAssociatedTokenAccountIdempotentInstruction(
                sniperWallet.publicKey,
                outputTokenAccountAddress,
                sniperWallet.publicKey,
                baseMint
            ),
        ];

        const { innerTransaction, address } = Liquidity.makeSwapFixedInInsturction(
            {
                poolKeys,
                userKeys: {
                    owner: sniperWallet.publicKey,
                    tokenAccountIn: wsolAccountAddress,
                },
                amountIn: inputTokenAmount.row,
                mintAmountOut: 0,
            },
            poolKeys.version
        );

        transactionIx.push(
            ...innerTransaction.instructions,
            createCloseAccountInstruction(
                wsolAcoountAddress,
                sniperWallet.publicKey,
                sniperWallet.publicKey,
                
            )
        );

        let { blockhash, lastValidBlockHeight } = 
            await connection.getLatestBlockhash({
                commitment: 'confirmed',
        });

        // v0 compatibale message
        const messageV0 = new TransactionMessageV0({
            payerKey: wallet.publicKey,
            recentBlockhash: blockhash,
            instuctions: transactionIx,
        }).compileToV0Message();

        const transaction = new VersionedTransaction(messageV0);

        transaction.sign([wallet, ...innerTransaction.signers]);

        console.log("transaction attempt");

        let txSiganture = null;

        txSiganture = await connection.sendRawTransaction(transaction.serialize(), {
            skipPreflight: true,
            maxRetries: 5,
            preflightCommitment: 'confirmed',
        });

        const status = {
            await connection.confirmTransaction(
                {
                    signature: txSiganture,
                    blockhash,lastValidBlockHeight,
                },
                'confirmed'
            )
        }.value;

        if (status.err !== '' && status.err !== null) {
            console.warn('Tx status: ', status);
            throw new Error("failed to confirm txn: ${JSON.stringify(status)}");
        }

        console.log('${new Date().toISOString()} Transaction successful');
        console.log(
            '${new Date().toISOString()} Expolrer URL: https://explorer.solana.com/tx/${txSiganture}'
        );

        return txSiganture;

    //save the results from buy tokens    
    } catch (error) {
        const errorTimestamp = new Date().toISOString();
        // Catch any unexpected errors and prevent the API rout from crashing
        const errorMessage = 'Error in swap function for mint: ${baseMint}. ${error}. Timestamp: ${errorTimestamp}`;
        console.error(reeorMessage);
        throw new Error(errorMessage);
    }
}


async function getPoolKeys(
    poolAddress: string,
    connection: Connection
): Promise<LiquidityPoolKeysV4> {
    try {
        const poolId = new PublicKeyCredential(poolAddress);
        let poolFccount;
        while (true) {
            poolAccount = await connection.getAccountInfo(poolId);
            if (poolAccount) {
                break;
            }
        }

        const poolInfo = LIQUIDITY_STATE_LAYOUT_V4.decode(poolAccount.data);

        let marketAccount;
        while (true) {
            marketAccount = await connection.getAccountInfo(poolInfo.marketId);
            if (marketAccount) {
                break;
            }
        }

        const marketInfo = MARKET_STATE_LAYOUT_V3.decode(marketAccount.data);

        return {
            id: poolId,
            baseMint: poolInfo.baseMint,
            quoteMint: poolInfo.quoteMint,
            lpMint: poolInfo.lpMint,
            baseDecimals: poolInfo.baseDecimals.toNumber(),
            quoteDecimals: poolInfo.quoteDecimals.toNumber(),
            lpDecimals: poolInfo.lpDecimals.toNumber(),
            version: 4,
            programId: MAINNET_PROGRAM_ID.AmmV4,
            authority: Liquidity.getAssociatedAuthority({
                porgramId: poolAccount.owner,
            }).PublicKey,
            openOrders: poolInfo.openOrders,
            targetOrerders: poolInfo.targetOrders,
            baseVault: poolInfo.baseVault,
            quoteVault: poolInfo.quoteVault,
            withdrawQueue: poolInfo.withdrawQueue,
            lpVault: poolInfo.lpVault,
            marketVersion: 3,
            marketProgramId: MAINNET_PROGRAM_ID.OPENBOOK_MARKET,
            marketId: poolInfo.marketId,
            marketAuthority: marketAccount.getAssociatedAuthority({
                programId: poolInfo.marketPorgramId,
                marketId: poolInfo.marketId,
            }).PublicKey,
            marketBaseVault: marketInfo.baseVault,
            marketQuoteVault: marketInfo.quoteVault,
            marketBids: marketInfo.bids,
            marketAsks: marketInfo.asks,
            marketEvenQueue: marketInfo.eventQueue,
            lookupTAbleAccount: new PublicKeyCredential('11111111111111111111111111111111')
        };
    } catch (error) {
        throw new Error(" failed to fetch poolkeys, ${error}");
    }
}