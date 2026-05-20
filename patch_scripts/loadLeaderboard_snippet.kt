    fun loadLeaderboard(boardId: String, kind: String) {
        if (!isSignedIn) {
            handler.post {
                webView.evaluateJavascript("TSLB.receiveData('" + kind + "',null,'not_signed_in');", null)
            }
            return
        }
        PlayGames.getLeaderboardsClient(this)
            .loadTopScores(boardId,
                LeaderboardVariant.TIME_SPAN_ALL_TIME,
                LeaderboardVariant.COLLECTION_PUBLIC, 25)
            .addOnSuccessListener { annotated ->
                val scores = annotated.get()
                if (scores == null) {
                    handler.post {
                        webView.evaluateJavascript("TSLB.receiveData('" + kind + "',null,'no_data');", null)
                    }
                    return@addOnSuccessListener
                }
                val buf = scores.scores
                val sb = StringBuilder("[")
                for (i in 0 until buf.count) {
                    val e = buf.get(i)
                    if (i > 0) sb.append(",")
                    val nm = e.scoreHolderDisplayName.replace("\"", "\\\"")
                    sb.append("{\"rank\":").append(e.rank)
                      .append(",\"name\":\"").append(nm)
                      .append("\",\"score\":").append(e.rawScore).append("}")
                }
                sb.append("]")
                val json = sb.toString()
                handler.post {
                    webView.evaluateJavascript("TSLB.receiveData('" + kind + "'," + json + ",'');", null)
                }
            }
            .addOnFailureListener {
                handler.post {
                    webView.evaluateJavascript("TSLB.receiveData('" + kind + "',null,'failed');", null)
                }
            }
    }

