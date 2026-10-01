import { getModelById, getVideoModelById, getI2IModelById, getI2VModelById, getV2VModelById, getLipSyncModelById } from './models.js';

export class CodgenClient {
    constructor() {
        // Phase 2: points to Codgen proxy backend — Muapi key never reaches the browser
        this.baseUrl = window.__CODGEN_BACKEND_URL__ || import.meta.env.VITE_BACKEND_URL || '';
    }

    getToken() {
        const token = window.__CODGEN_TOKEN__ || localStorage.getItem('codgen_token');
        if (!token) throw new Error('Not authenticated. Please log in.');
        return token;
    }

    authHeaders() {
        return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${this.getToken()}` };
    }

    /**
     * Generates an image (Text-to-Image or Image-to-Image)
     * @param {Object} params
     * @param {string} params.model
     * @param {string} params.prompt
     * @param {string} params.negative_prompt
     * @param {string} params.aspect_ratio
     * @param {number} params.steps
     * @param {number} params.guidance_scale
     * @param {number} params.seed
     * @param {string} [params.image_url] - If present, treats as Image-to-Image
     */
    async generateImage(params) {

        // Resolve endpoint from model definition
        const modelInfo = getModelById(params.model);
        const endpoint = modelInfo?.endpoint || params.model;
        const url = `${this.baseUrl}/api/v1/${endpoint}`;

        // Build payload matching the API's expected format
        const finalPayload = {
            prompt: params.prompt,
        };

        // Aspect ratio (send as string, the API handles it)
        if (params.aspect_ratio) {
            finalPayload.aspect_ratio = params.aspect_ratio;
        }

        // Resolution
        if (params.resolution) {
            finalPayload.resolution = params.resolution;
        }

        // Quality (used by seedream and similar models)
        if (params.quality) {
            finalPayload.quality = params.quality;
        }

        // Image-to-Image
        if (params.image_url) {
            finalPayload.image_url = params.image_url;
            finalPayload.strength = params.strength || 0.6;
        } else {
            finalPayload.image_url = null;
        }

        // Optional params if supported by model
        if (params.seed && params.seed !== -1) {
            finalPayload.seed = params.seed;
        }

        console.log('[Codgen] Requesting:', url);
        console.log('[Codgen] Payload:', finalPayload);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: this.authHeaders(),
                body: JSON.stringify(finalPayload)
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Request Failed: ${response.status} ${response.statusText} - ${errText.slice(0, 100)}`);
            }

            const submitData = await response.json();
            const requestId = submitData.request_id || submitData.id;
            if (!requestId) return submitData;

            if (params.onRequestId) params.onRequestId(requestId);

            const result = await this.pollForResult(requestId);
            const imageUrl = result.outputs?.[0] || result.url || result.output?.url;
            return { ...result, url: imageUrl };

        } catch (error) {
            console.error('[Codgen] generateImage error:', error);
            throw error;
        }
    }

    /**
     * Polls the predictions endpoint until the result is ready.
     * @param {string} requestId - The request ID from the submit response
     * @param {string} key - The API key
     * @param {number} maxAttempts - Maximum polling attempts (default 60 = ~2 min)
     * @param {number} interval - Polling interval in ms (default 2000)
     */
    async pollForResult(requestId, _unused, maxAttempts = 60, interval = 2000) {
        const pollUrl = `${this.baseUrl}/api/v1/predictions/${requestId}/result`;

        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            await new Promise(resolve => setTimeout(resolve, interval));
            try {
                const response = await fetch(pollUrl, { headers: this.authHeaders() });

                if (!response.ok) {
                    const errText = await response.text();
                    if (response.status >= 500) continue;
                    throw new Error(`Poll Failed: ${response.status} - ${errText.slice(0, 100)}`);
                }

                const data = await response.json();
                const status = data.status?.toLowerCase();

                if (status === 'completed' || status === 'succeeded' || status === 'success') return data;
                if (status === 'failed' || status === 'error') throw new Error(`Generation failed: ${data.error || 'Unknown error'}`);
            } catch (error) {
                if (attempt === maxAttempts) throw error;
            }
        }

        throw new Error('Generation timed out after polling.');
    }

    async generateVideo(params) {

        const modelInfo = getVideoModelById(params.model);
        const endpoint = modelInfo?.endpoint || params.model;
        const url = `${this.baseUrl}/api/v1/${endpoint}`;

        const finalPayload = {};

        if (params.prompt) finalPayload.prompt = params.prompt;
        if (params.request_id) finalPayload.request_id = params.request_id;
        if (params.aspect_ratio) finalPayload.aspect_ratio = params.aspect_ratio;
        if (params.duration) finalPayload.duration = params.duration;
        if (params.resolution) finalPayload.resolution = params.resolution;
        if (params.quality) finalPayload.quality = params.quality;
        if (params.mode) finalPayload.mode = params.mode;
        if (params.image_url) finalPayload.image_url = params.image_url;

        console.log('[Codgen] Video Request:', url);
        console.log('[Codgen] Video Payload:', finalPayload);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: this.authHeaders(),
                body: JSON.stringify(finalPayload)
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Request Failed: ${response.status} ${response.statusText} - ${errText.slice(0, 100)}`);
            }

            const submitData = await response.json();
            const requestId = submitData.request_id || submitData.id;
            if (!requestId) return submitData;

            if (params.onRequestId) params.onRequestId(requestId);

            const result = await this.pollForResult(requestId, null, 900, 2000);
            const videoUrl = result.outputs?.[0] || result.url || result.output?.url;
            return { ...result, url: videoUrl };

        } catch (error) {
            console.error('[Codgen] generateVideo error:', error);
            throw error;
        }
    }

    /**
     * Generates an image using an Image-to-Image model.
     * The model's imageField determines which payload key receives the uploaded image URL.
     * @param {Object} params
     * @param {string} params.model - i2iModel id
     * @param {string} params.image_url - The uploaded reference image URL
     * @param {string} [params.prompt] - Optional text prompt
     * @param {string} [params.aspect_ratio]
     * @param {string} [params.resolution]
     */
    async generateI2I(params) {
        const modelInfo = getI2IModelById(params.model);
        const endpoint = modelInfo?.endpoint || params.model;
        const url = `${this.baseUrl}/api/v1/${endpoint}`;

        const finalPayload = {};

        // Only include prompt if the model supports it and one was provided
        if (params.prompt) finalPayload.prompt = params.prompt;

        // Place the uploaded image(s) in the correct field for this model
        const imageField = modelInfo?.imageField || 'image_url';
        const imagesList = params.images_list?.length > 0 ? params.images_list : (params.image_url ? [params.image_url] : null);
        if (imagesList) {
            if (imageField === 'images_list') {
                finalPayload.images_list = imagesList;
            } else {
                finalPayload[imageField] = imagesList[0];
            }
        }

        if (params.aspect_ratio) finalPayload.aspect_ratio = params.aspect_ratio;
        if (params.resolution) finalPayload.resolution = params.resolution;
        if (params.quality) finalPayload.quality = params.quality;

        console.log('[Codgen] I2I Request:', url);
        console.log('[Codgen] I2I Payload:', finalPayload);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: this.authHeaders(),
                body: JSON.stringify(finalPayload)
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Request Failed: ${response.status} ${response.statusText} - ${errText.slice(0, 100)}`);
            }

            const submitData = await response.json();
            const requestId = submitData.request_id || submitData.id;
            if (!requestId) return submitData;

            if (params.onRequestId) params.onRequestId(requestId);

            const result = await this.pollForResult(requestId);
            const imageUrl = result.outputs?.[0] || result.url || result.output?.url;
            return { ...result, url: imageUrl };
        } catch (error) {
            console.error('[Codgen] generateI2I error:', error);
            throw error;
        }
    }

    /**
     * Generates a video using an Image-to-Video model.
     * @param {Object} params
     * @param {string} params.model - i2vModel id
     * @param {string} params.image_url - The uploaded start frame image URL
     * @param {string} [params.prompt]
     * @param {string} [params.aspect_ratio]
     * @param {string} [params.resolution]
     * @param {number} [params.duration]
     * @param {string} [params.quality]
     */
    async generateI2V(params) {
        const modelInfo = getI2VModelById(params.model);
        const endpoint = modelInfo?.endpoint || params.model;
        const url = `${this.baseUrl}/api/v1/${endpoint}`;

        const finalPayload = {};

        if (params.prompt) finalPayload.prompt = params.prompt;

        // Place image in the correct field for this model
        const imageField = modelInfo?.imageField || 'image_url';
        if (params.image_url) {
            if (imageField === 'images_list') {
                finalPayload.images_list = [params.image_url];
            } else {
                finalPayload[imageField] = params.image_url;
            }
        }

        if (params.aspect_ratio) finalPayload.aspect_ratio = params.aspect_ratio;
        if (params.duration) finalPayload.duration = params.duration;
        if (params.resolution) finalPayload.resolution = params.resolution;
        if (params.quality) finalPayload.quality = params.quality;
        if (params.mode) finalPayload.mode = params.mode;

        console.log('[Codgen] I2V Request:', url);
        console.log('[Codgen] I2V Payload:', finalPayload);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: this.authHeaders(),
                body: JSON.stringify(finalPayload)
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Request Failed: ${response.status} ${response.statusText} - ${errText.slice(0, 100)}`);
            }

            const submitData = await response.json();
            const requestId = submitData.request_id || submitData.id;
            if (!requestId) return submitData;

            if (params.onRequestId) params.onRequestId(requestId);

            const result = await this.pollForResult(requestId, null, 900, 2000);
            const videoUrl = result.outputs?.[0] || result.url || result.output?.url;
            return { ...result, url: videoUrl };
        } catch (error) {
            console.error('[Codgen] generateI2V error:', error);
            throw error;
        }
    }

    /**
     * Uploads a file and returns the hosted URL.
     * @param {File} file - The image file to upload
     * @returns {Promise<string>} The hosted URL of the uploaded file
     */
    async uploadFile(file) {
        const url = `${this.baseUrl}/api/v1/upload_file`;
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${this.getToken()}` },
            body: formData
        });

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`File upload failed: ${response.status} - ${errText.slice(0, 100)}`);
        }

        const data = await response.json();
        const fileUrl = data.url || data.file_url || data.data?.url;
        if (!fileUrl) throw new Error('No URL returned from file upload');
        return fileUrl;
    }

    /**
     * Processes a video through a Video-to-Video model (e.g. watermark remover).
     * @param {Object} params
     * @param {string} params.model - v2vModel id
     * @param {string} params.video_url - The uploaded video URL
     */
    async processV2V(params) {
        const modelInfo = getV2VModelById(params.model);
        const endpoint = modelInfo?.endpoint || params.model;
        const url = `${this.baseUrl}/api/v1/${endpoint}`;

        const videoField = modelInfo?.videoField || 'video_url';
        const finalPayload = { [videoField]: params.video_url };

        console.log('[Codgen] V2V Request:', url);
        console.log('[Codgen] V2V Payload:', finalPayload);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: this.authHeaders(),
                body: JSON.stringify(finalPayload)
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Request Failed: ${response.status} ${response.statusText} - ${errText.slice(0, 100)}`);
            }

            const submitData = await response.json();
            const requestId = submitData.request_id || submitData.id;
            if (!requestId) return submitData;

            if (params.onRequestId) params.onRequestId(requestId);

            const result = await this.pollForResult(requestId, null, 900, 2000);
            const videoUrl = result.outputs?.[0] || result.url || result.output?.url;
            return { ...result, url: videoUrl };
        } catch (error) {
            console.error('[Codgen] processV2V error:', error);
            throw error;
        }
    }

    /**
     * Processes lipsync / speech-to-video generation.
     * Supports image+audio → video and video+audio → video models.
     * @param {Object} params
     * @param {string} params.model - lipsyncModel id
     * @param {string} [params.image_url] - Portrait image URL (image-based models)
     * @param {string} [params.video_url] - Source video URL (video-based models)
     * @param {string} params.audio_url - Audio file URL
     * @param {string} [params.prompt] - Optional prompt (for models that support it)
     * @param {string} [params.resolution] - Output resolution
     * @param {number} [params.seed] - Optional seed (-1 for random)
     * @param {Function} [params.onRequestId] - Called when request_id is received
     */
    async processLipSync(params) {
        const modelInfo = getLipSyncModelById(params.model);
        const endpoint = modelInfo?.endpoint || params.model;
        const url = `${this.baseUrl}/api/v1/${endpoint}`;

        const finalPayload = {};

        if (params.audio_url) finalPayload.audio_url = params.audio_url;
        if (params.image_url) finalPayload.image_url = params.image_url;
        if (params.video_url) finalPayload.video_url = params.video_url;
        if (params.prompt) finalPayload.prompt = params.prompt;
        if (params.resolution) finalPayload.resolution = params.resolution;
        if (params.seed !== undefined && params.seed !== -1) finalPayload.seed = params.seed;

        console.log('[Codgen] LipSync Request:', url);
        console.log('[Codgen] LipSync Payload:', finalPayload);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: this.authHeaders(),
                body: JSON.stringify(finalPayload)
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Request Failed: ${response.status} ${response.statusText} - ${errText.slice(0, 100)}`);
            }

            const submitData = await response.json();
            const requestId = submitData.request_id || submitData.id;
            if (!requestId) return submitData;

            if (params.onRequestId) params.onRequestId(requestId);

            const result = await this.pollForResult(requestId, null, 900, 2000);
            const videoUrl = result.outputs?.[0] || result.url || result.output?.url;
            return { ...result, url: videoUrl };
        } catch (error) {
            console.error('[Codgen] processLipSync error:', error);
            throw error;
        }
    }

    getDimensionsFromAR(ar) {
        // Base unit 1024 (Flux standard)
        switch (ar) {
            case '1:1': return [1024, 1024];
            case '16:9': return [1280, 720]; // 1024*1024 area approx
            case '9:16': return [720, 1280];
            case '4:3': return [1152, 864];
            case '3:2': return [1216, 832];
            case '21:9': return [1536, 640];
            default: return [1024, 1024];
        }
    }
}

export const codgen = new CodgenClient();
// backward-compat alias
export const muapi = codgen;
