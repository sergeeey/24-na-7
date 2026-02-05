/**
 * Smart Replay Component
 * Reflexio 24/7 — November 2025 Integration Sprint
 * 
 * Компонент для поиска по аудио с embeddings и навигацией к таймкоду
 */

import React, { useState, useEffect } from 'react';

const SmartReplay = ({ audioId, apiUrl = 'http://localhost:8000' }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [audioPlayer, setAudioPlayer] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);
  
  // Кэш для результатов поиска
  const searchCache = React.useRef(new Map());
  const CACHE_TTL = 5 * 60 * 1000; // 5 минут

  // Поиск по фразам через embeddings с кэшированием
  const searchPhrases = async (query) => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }

    // Проверяем кэш
    const cacheKey = `${audioId}:${query.toLowerCase()}`;
    const cached = searchCache.current.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      setSearchResults(cached.results);
      return;
    }

    setIsSearching(true);
    
    try {
      const startTime = performance.now();
      
      const response = await fetch(`${apiUrl}/search/phrases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          audio_id: audioId,
          query: query,
          limit: 10,
        }),
      });

      if (response.ok) {
        const results = await response.json();
        const matches = results.matches || [];
        
        // Сохраняем в кэш
        searchCache.current.set(cacheKey, {
          results: matches,
          timestamp: Date.now(),
        });
        
        setSearchResults(matches);
        
        const latency = performance.now() - startTime;
        if (latency > 2000) {
          console.warn(`Search latency: ${latency.toFixed(2)}ms (target: < 2000ms)`);
        }
      }
    } catch (error) {
      console.error('Error searching phrases:', error);
    } finally {
      setIsSearching(false);
    }
  };

  // Навигация к таймкоду
  const navigateToTimestamp = (timestamp) => {
    if (audioPlayer) {
      audioPlayer.currentTime = timestamp;
      audioPlayer.play();
    }
  };

  useEffect(() => {
    const player = document.getElementById(`audio-player-${audioId}`);
    if (player) {
      setAudioPlayer(player);
      player.addEventListener('timeupdate', () => {
        setCurrentTime(player.currentTime);
      });
    }
  }, [audioId]);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="smart-replay">
      <div className="search-box">
        <input
          type="text"
          placeholder="Поиск по фразам..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === 'Enter') {
              searchPhrases(searchQuery);
            }
          }}
        />
        <button onClick={() => searchPhrases(searchQuery)} disabled={isSearching}>
          {isSearching ? 'Поиск...' : '🔍'}
        </button>
      </div>

      {searchResults.length > 0 && (
        <div className="search-results">
          <h3>Найденные фразы:</h3>
          <ul>
            {searchResults.map((result, index) => (
              <li key={index} className="search-result-item">
                <div className="result-text">{result.text}</div>
                <div className="result-meta">
                  <span className="timestamp">{formatTime(result.start)}</span>
                  <button
                    className="jump-button"
                    onClick={() => navigateToTimestamp(result.start)}
                  >
                    Перейти
                  </button>
                  {result.confidence && (
                    <span className="confidence">
                      Confidence: {(result.confidence * 100).toFixed(1)}%
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <audio
        id={`audio-player-${audioId}`}
        controls
        src={`${apiUrl}/audio/${audioId}`}
      />
    </div>
  );
};

export default SmartReplay;

