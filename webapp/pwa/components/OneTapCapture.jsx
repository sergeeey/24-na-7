/**
 * One-Tap Capture Component
 * Reflexio 24/7 — November 2025 Integration Sprint
 * 
 * Компонент для быстрого старта записи (< 300 мс)
 */

import React, { useState, useRef, useEffect } from 'react';

const OneTapCapture = ({ apiUrl = 'http://localhost:8000', onRecordingComplete }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('idle'); // idle | uploading | success | error
  const [recordingTime, setRecordingTime] = useState(0);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerRef = useRef(null);

  // Предзагрузка MediaRecorder для быстрого старта (< 300 мс)
  const preloadMediaRecorder = useRef(null);
  const preloadedStream = useRef(null);
  
  useEffect(() => {
    // Предзагружаем доступ к микрофону при монтировании компонента
    const preload = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          audio: {
            sampleRate: 16000,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true, // Добавляем AGC для лучшего качества
          } 
        });
        
        preloadedStream.current = stream;
        
        // Создаём MediaRecorder заранее
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
          ? 'audio/webm;codecs=opus'
          : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : 'audio/mp4';
        
        const mediaRecorder = new MediaRecorder(stream, { mimeType });
        preloadMediaRecorder.current = mediaRecorder;
        
        // Настраиваем обработчики заранее
        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data);
          }
        };
        
        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
          await uploadAudio(audioBlob);
          
          // Останавливаем все треки
          if (preloadedStream.current) {
            preloadedStream.current.getTracks().forEach(track => track.stop());
            preloadedStream.current = null;
          }
        };
        
      } catch (error) {
        console.warn('Preload failed, will request on demand:', error);
      }
    };
    
    preload();
    
    // Cleanup при размонтировании
    return () => {
      if (preloadedStream.current) {
        preloadedStream.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);
  
  // Запрос доступа к микрофону (оптимизированная версия)
  const startRecording = async () => {
    const startTime = performance.now();
    
    try {
      let stream = preloadedStream.current;
      let mediaRecorder = preloadMediaRecorder.current;
      
      // Если предзагрузка не удалась, запрашиваем доступ
      if (!stream || !mediaRecorder) {
        stream = await navigator.mediaDevices.getUserMedia({ 
          audio: {
            sampleRate: 16000,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          } 
        });
        
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
          ? 'audio/webm;codecs=opus'
          : 'audio/webm';
        
        mediaRecorder = new MediaRecorder(stream, { mimeType });
        
        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data);
          }
        };
        
        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
          await uploadAudio(audioBlob);
          stream.getTracks().forEach(track => track.stop());
        };
      }
      
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      
      mediaRecorder.start();
      setIsRecording(true);
      setUploadStatus('idle');
      
      const latency = performance.now() - startTime;
      if (latency > 300) {
        console.warn(`Recording start latency: ${latency.toFixed(2)}ms (target: < 300ms)`);
      }
      
      // Таймер записи
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
      
    } catch (error) {
      console.error('Error starting recording:', error);
      setUploadStatus('error');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    }
  };

  const uploadAudio = async (audioBlob) => {
    setUploadStatus('uploading');
    
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, `recording-${Date.now()}.webm`);
      
      const response = await fetch(`${apiUrl}/ingest/audio`, {
        method: 'POST',
        body: formData,
      });
      
      if (response.ok) {
        const result = await response.json();
        setUploadStatus('success');
        setRecordingTime(0);
        
        if (onRecordingComplete) {
          onRecordingComplete(result);
        }
      } else {
        throw new Error('Upload failed');
      }
    } catch (error) {
      console.error('Error uploading audio:', error);
      setUploadStatus('error');
    }
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="one-tap-capture">
      <button
        className={`record-button ${isRecording ? 'recording' : ''}`}
        onMouseDown={startRecording}
        onMouseUp={stopRecording}
        onTouchStart={startRecording}
        onTouchEnd={stopRecording}
        disabled={uploadStatus === 'uploading'}
      >
        {isRecording ? '⏹️' : '🎤'}
      </button>
      
      {isRecording && (
        <div className="recording-status">
          <span className="recording-indicator">●</span>
          <span>{formatTime(recordingTime)}</span>
        </div>
      )}
      
      {uploadStatus === 'uploading' && (
        <div className="upload-status">Загрузка...</div>
      )}
      
      {uploadStatus === 'success' && (
        <div className="upload-status success">✓ Загружено</div>
      )}
      
      {uploadStatus === 'error' && (
        <div className="upload-status error">✗ Ошибка</div>
      )}
    </div>
  );
};

export default OneTapCapture;

