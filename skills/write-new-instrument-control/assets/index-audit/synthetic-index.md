# Synthetic command index (fixture)

This table is synthetic and exists only for offline tests. It is not a vendor
command list.

| Command | Type | Notes |
|---|---|---|
| `:RUN` | event | documented |
| `*IDN?` | query | documented |
| `[:SOURce[<n>]]:VOLTage[:DC]` | set | documented |
| `:CHANnel<n>:SCALe` | set/query | documented |
| `:MEASure` | family | documented family form |
| `:MEASure:VPP?` | query | hardware-verified |
| `:FUNCtion:FFT` | set/query | documented |
| `:ABORt:CONFigure` | event | documented |
| `:TRIGger:EDGE:SOURce` | set/query | documented |
| `:TRIGger:EDGE:SLOPe` | set/query | documented |
| `:STOP` | event | documented |
| `:WAVEform:DATA?` | query | hardware-verified |
